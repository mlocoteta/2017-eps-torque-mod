/*
 * accord17_tap -- passive LKAS<->EPS serial logger for the 2016/2017 Accord
 * Teensy 4.0 on the V1 "LKAS/ECU Manipulator" + Debug IO board.
 *
 * PURPOSE
 *   Capture BOTH serial directions byte-exactly, with microsecond timestamps,
 *   frame-gap timing and error counters, and stream them to a laptop for
 *   saving. Decoding happens OFFLINE in Python against
 *   analysis-2017accord/model/honda_serial_model.py -- never here, so the
 *   firmware and the analysis cannot silently diverge.
 *
 * SAFETY POSTURE
 *   PURE PASSIVE TAP. Every byte received on each line is re-transmitted on
 *   the opposite line unmodified, in order, BEFORE anything else happens to
 *   it. There is no code path in this file that synthesises or alters a
 *   steering command.
 *
 * >>> THE RULE THAT SHAPES THIS FILE <<<
 *   LOGGING MUST NEVER BLOCK PASS-THROUGH. Teensy USB serial blocks when the
 *   host is connected but not draining its buffer. If a formatted print sat
 *   in the receive path, a stalled terminal would delay the car's own bytes,
 *   and a late frame on this link is precisely what faults the EPS.
 *   So: capture appends fixed-size records to a RAM ring and returns. A
 *   separate drain stage formats them only when the USB TX buffer has room,
 *   and DROPS (counting) rather than waits. A lost log line is a nuisance;
 *   a delayed steering frame is a fault.
 *
 * WIRING -- taken verbatim from the two known-working Teensy sketches
 *   (reddn/AccordLinDataReader, A_HondaSteering_Setup.ino). Both run on this
 *   board. Confirm against your schematic before the first drive.
 *     Serial2 = EPStoLKAS  (from the power steering, 5 bytes/frame)
 *     Serial3 = LKAStoEPS  (from the camera,         4 bytes/frame)
 *     9600 8E1  (8 data bits, EVEN parity, 1 stop)
 *
 *   NOTE: Teensy 4.0 has no SD socket, and the Debug IO board carries only a
 *   pot, 4 buttons and a DIP block. Capture is USB-to-laptop; use
 *   analysis-2017accord/tools/capture_tap.py to save the stream.
 */

#include <Arduino.h>

// ---- hardware watchdog, i.MX RT1062 WDOG1 --------------------------------
// There is no Watchdog_t4 in this framework version, so WDOG1 is driven
// directly; imxrt.h defines the registers and the Teensy core never touches
// them. Timeout = (WT + 1) * 0.5 s, so WT=0 is the 0.5 s minimum. The loop
// runs in microseconds, five orders of magnitude of margin.
//
// WDE (bit 2) enables it and CANNOT be cleared except by a reset -- one-way
// by design. SRS (bit 4) and WDA (bit 5) are left SET, which is their
// not-asserted state; clearing either would trigger the thing we are trying
// to guard against.
static inline void wdt_begin_500ms(void) {
  WDOG1_WCR = (0u << 8) | (1u << 2) | (1u << 4) | (1u << 5);
}
static inline void wdt_feed(void) {
  WDOG1_WSR = 0x5555;
  WDOG1_WSR = 0xAAAA;
}
// WRSR, latched at boot: bit0 SFTW (software), bit1 TOUT (watchdog timeout),
// bit4 POR (power-on). Read BEFORE enabling, reported in the banner, so a
// mid-drive reboot is visible in the log instead of silently losing frames.
static uint16_t bootWrsr = 0;

#define EPStoLKAS_Serial  Serial2
#define LKAStoEPS_Serial  Serial3
#define out               Serial

// ---- Debug IO board ------------------------------------------------------
#define PB1  2            // press = drop a MARK record into the log
#define PB2  3
#define PB3  4
#define PB4  5
#define DIP1 6            // ON = append derived columns for live eyeballing
#define DIP2 32           // ON = emit a heartbeat line every second
#define BLUE_LED 28

#define LINK_BAUD    9600
#define LINK_CONFIG  SERIAL_8E1
// Idle backstop only -- NOT the primary framing rule.
//
// MEASURED on the car (2026-11-13_002058_base.csv, 91 947 bytes):
//   inter-BYTE gap   median 2001 us, p99 5736 us   <- the ECU paces bytes;
//                                                     a byte itself is 1146 us
//   inter-FRAME gap  median 10000 us, min 7713 us
//
// The old 2000 us was SHORTER than the typical inter-byte gap, so every frame
// was chopped into 1-2 byte fragments. Worse, the honest window between p99
// inter-byte (5736) and min inter-frame (7713) is only ~2 ms, too thin to sit
// a threshold in. So the gap is now a pure "line went quiet" flush, and the
// top-nibble<4 sync rule does the framing -- which it does perfectly:
// 10 215/10 215 LKAS and 10 215/10 215 EPS frames checksum-valid with the gap
// rule effectively disabled.
#define FRAME_GAP_US 50000
#define MAXFRAME     8
#define RING_SZ      1024      // 1024 * 16B = 16 KB of the Teensy's 1 MB

// A frame starts on a byte whose TOP NIBBLE IS < 4. Every other byte in both
// directions has top nibble >= 4 by construction -- on the camera->EPS side
// the checksum's (%128)+128 guarantees it. EVIDENCE: 20124 frames across six
// stock captures, zero sync violations, zero checksum failures.
static inline bool isFrameStart(uint8_t b) { return (b >> 4) < 4; }

// ---------------------------------------------------------------- record
enum { R_FRAME = 0, R_MARK = 1 };

struct Rec {
  uint32_t t;             // micros() of first byte
  uint32_t gap;           // since previous frame's first byte, same line
  uint16_t span;          // first byte -> last byte
  uint8_t  kind;          // R_FRAME | R_MARK
  uint8_t  dir;           // 'L' | 'E' | 'M'
  uint8_t  n;
  uint8_t  b[5];
};                        // 16 bytes

static Rec      ring[RING_SZ];
static volatile uint16_t r_head = 0, r_tail = 0;
static uint32_t dropped = 0;

static inline void push(const Rec &r) {
  uint16_t nxt = (uint16_t)((r_head + 1) % RING_SZ);
  if (nxt == r_tail) { dropped++; return; }   // FULL: drop, never block
  ring[r_head] = r;
  r_head = nxt;
}

// ---------------------------------------------------------------- tap
struct Tap {
  char     name;
  uint8_t  buf[MAXFRAME];
  uint8_t  n;
  uint32_t t_first;
  uint32_t t_prev_frame;
  uint32_t frames;
  uint32_t overruns;      // frame ran past MAXFRAME => desync
};

static Tap tapL = { 'L', {0}, 0, 0, 0, 0, 0 };
static Tap tapE = { 'E', {0}, 0, 0, 0, 0, 0 };

static uint32_t t0, lastHeartbeat, lastBlink;
static volatile bool bannerPending = false;
#define BANNER_BYTES 320

static bool     verbose;

static void closeFrame(Tap *t, uint32_t t_last) {
  Rec r;
  r.t    = t->t_first;
  r.gap  = (t->t_prev_frame == 0) ? 0 : (t->t_first - t->t_prev_frame);
  uint32_t sp = t_last - t->t_first;
  r.span = (sp > 65535) ? 65535 : (uint16_t)sp;
  r.kind = R_FRAME;
  r.dir  = (uint8_t)t->name;
  r.n    = t->n;
  for (uint8_t i = 0; i < 5; i++) r.b[i] = (i < t->n) ? t->buf[i] : 0;
  push(r);
  t->t_prev_frame = t->t_first;
  t->frames++;
  t->n = 0;
}

// Receive path. Relay FIRST and unconditionally, then buffer. No formatting,
// no printing, no blocking calls.
static void pump(Tap *t, HardwareSerial &in, HardwareSerial &relayTo) {
  while (in.available()) {
    uint32_t now = micros();
    uint8_t  b   = in.read();

    relayTo.write(b);                       // <-- the car's path, first

    bool boundary = isFrameStart(b) ||
                    (t->n > 0 && (now - t->t_first) > FRAME_GAP_US) ||
                    (t->n >= MAXFRAME);

    if (boundary && t->n > 0) {
      if (t->n >= MAXFRAME) t->overruns++;
      closeFrame(t, now);
    }
    if (t->n == 0) t->t_first = now;
    if (t->n < MAXFRAME) t->buf[t->n++] = b;
  }
}

// A frame is only closed when the next one starts, so a line going quiet
// would hold its last frame forever. Flush on idle.
static void flushIdle(Tap *t) {
  if (t->n > 0 && (micros() - t->t_first) > FRAME_GAP_US) {
    closeFrame(t, micros());
  }
}

static void pushMark(char src) {
  Rec r; r.t = micros(); r.gap = 0; r.span = 0;
  r.kind = R_MARK; r.dir = 'M'; r.n = 1;
  r.b[0] = (uint8_t)src; r.b[1] = r.b[2] = r.b[3] = r.b[4] = 0;
  push(r);
}

// ---------------------------------------------------------------- drain
// Format and emit at most a few records per loop, only while the USB TX
// buffer can take a full line without blocking.
#define LINE_MAX 96

// snprintf returns what it WOULD have written, so a naive `k += snprintf(...)`
// can push k past the buffer; the next call then passes a NEGATIVE size that
// converts to a huge size_t and overruns. Clamp after every append.
#define APPEND(...)                                                           \
  do {                                                                        \
    if (k < (int)sizeof(line) - 1) {                                          \
      int _r = snprintf(line + k, sizeof(line) - k, __VA_ARGS__);             \
      k = (_r < 0) ? k : k + _r;                                              \
      if (k > (int)sizeof(line) - 1) k = (int)sizeof(line) - 1;               \
    }                                                                         \
  } while (0)

static void drain() {
  // The banner is text, not a Rec, so it is emitted here where the USB buffer
  // is checked -- never straight from loop().
  if (bannerPending && out.availableForWrite() >= BANNER_BYTES) {
    bannerPending = false;
    out.println("# accord17_tap v4 -- PASSIVE TAP, no command synthesis");
    out.println("# link 9600 8E1 | L=camera->EPS (4B) | E=EPS->camera (5B)");
    out.print  ("# cols: t_us,dir,gap_us,span_us,n,b0,b1,b2,b3,b4,overruns,dropped");
    out.println(verbose ? ",derived..." : "");
    out.print  ("# uptime_us="); out.print(micros() - t0);
    out.print  (" verbose=");    out.print(verbose ? 1 : 0);
    out.print  (" framesL=");    out.print(tapL.frames);
    out.print  (" framesE=");    out.print(tapE.frames);
    out.print  (" dropped=");    out.print(dropped);
    out.print  (" wrsr=0x");     out.print(bootWrsr, HEX);
    out.print  ((bootWrsr & 0x02) ? " WATCHDOG_RESET" : "");
    out.println((bootWrsr & 0x10) ? " poweron" : "");
  }

  uint8_t budget = 8;
  while (budget-- && r_tail != r_head) {
    if (out.availableForWrite() < LINE_MAX) return;   // no room: come back later

    Rec &r = ring[r_tail];
    char line[LINE_MAX];
    int  k = 0;

    if (r.kind == R_MARK) {
      APPEND("%lu,MARK,0,0,1,%02X,na,na,na,na,0,0,%lu\n",
             (unsigned long)(r.t - t0), r.b[0], (unsigned long)dropped);
    } else {
      APPEND("%lu,%c,%lu,%u,%u", (unsigned long)(r.t - t0), (char)r.dir,
             (unsigned long)r.gap, r.span, r.n);
      for (uint8_t i = 0; i < 5; i++) {
        if (i < r.n) APPEND(",%02X", r.b[i]);
        else         APPEND(",na");
      }
      uint32_t ovr = (r.dir == 'L') ? tapL.overruns : tapE.overruns;
      APPEND(",%lu,%lu", (unsigned long)ovr, (unsigned long)dropped);

      if (verbose && r.dir == 'L' && r.n >= 4) {
        int16_t v = ((r.b[0] & 0x07) << 5) | (r.b[1] & 0x1F);
        if ((r.b[0] >> 3) & 1) v |= 0xFF00;
        uint8_t sum = (uint8_t)(r.b[0] + r.b[1] + r.b[2]);
        uint8_t ck  = (uint8_t)((uint8_t)(256 - sum) % 128 + 128);
        APPEND(",steer=%d,on=%d,chk=%s", v, (r.b[1] >> 5) & 1,
               ck == r.b[3] ? "ok" : "BAD");
      }
      APPEND("\n");
    }

    out.write((const uint8_t *)line, k);
    r_tail = (uint16_t)((r_tail + 1) % RING_SZ);
  }
}

// ---------------------------------------------------------------- banner
// Emitted on EVERY host attach, not just at boot: Teensy USB discards output
// when nothing is listening, so a banner printed only in setup() is gone by
// the time a capture starts and every log would arrive with no column
// contract.
//
// It is a FLAG, not a call. The previous version printed it straight from
// loop() with ~10 unguarded out.print()s. Teensy USB serial BLOCKS when a
// host is attached but not draining, so a terminal that opened and then
// stalled would have held loop() -- and therefore the relay -- for as long as
// it stalled. drain() emits this only when the USB buffer provably has room.

// ---------------------------------------------------------------- setup
void setup() {
  pinMode(PB1, INPUT_PULLUP); pinMode(PB2, INPUT_PULLUP);
  pinMode(PB3, INPUT_PULLUP); pinMode(PB4, INPUT_PULLUP);
  pinMode(DIP1, INPUT_PULLUP); pinMode(DIP2, INPUT_PULLUP);
  pinMode(BLUE_LED, OUTPUT);

  // Settle the input pullups before sampling the DIPs. Microseconds, not the
  // delay(300) this used to carry -- that was 300 ms during which the UARTs
  // were already receiving and NOTHING was relaying. At 9600 8E1 that is
  // ~260 bytes, far past the RX buffer, and six times the 50 ms staleness
  // window the production firmware treats as a fault.
  delayMicroseconds(200);
  verbose = (digitalRead(DIP1) == LOW);

  out.begin(921600);                 // Teensy USB ignores this; kept for clarity
  EPStoLKAS_Serial.begin(LINK_BAUD, LINK_CONFIG);
  LKAStoEPS_Serial.begin(LINK_BAUD, LINK_CONFIG);

  t0 = micros();
  bannerPending = true;     // emitted by drain(), never inline

  // If loop() ever hangs, the relay stops and the car loses its steering link
  // with no recovery. The production STM32 firmware carried a 12 ms watchdog
  // for exactly this reason. 100 ms here: far longer than any real loop pass
  // (which is microseconds), short enough that a hang self-recovers through a
  // reboot instead of staying dead for the rest of the drive.
  bootWrsr = WDOG1_WRSR;             // read the reset cause BEFORE enabling
  wdt_begin_500ms();
}

// ----------------------------------------------------------------- loop
void loop() {
  wdt_feed();
  pump(&tapL, LKAStoEPS_Serial, EPStoLKAS_Serial);
  pump(&tapE, EPStoLKAS_Serial, LKAStoEPS_Serial);
  flushIdle(&tapL);
  flushIdle(&tapE);

  // Re-emit the column contract whenever a capture host attaches. `(bool)out`
  // is Teensy's DTR state, so this fires once per terminal that opens the port.
  // Sets a FLAG only -- the previous version did `delay(2); banner();` right
  // here, a 2 ms hard stall of the relay (~2 byte times at 9600) plus ten
  // unguarded blocking prints, every time a terminal opened.
  static bool hostWasUp = false;
  bool hostUp = (bool)out;
  if (hostUp && !hostWasUp) {
    bannerPending = true;
    // Records pushed while no host was listening were dropped by design --
    // USB discards output when nothing is attached. Zero the counter so
    // `dropped` means "lost during THIS capture", which is the only reading
    // that tells you whether the log you are holding is trustworthy. The
    // first real capture showed dropped=48004 before a single byte was
    // recorded, which looks alarming and means nothing.
    dropped = 0;
  }
  hostWasUp = hostUp;

  drain();

  // Marks: four buttons, plus any keystroke from the laptop.
  static bool p[4] = {false, false, false, false};
  const uint8_t pins[4] = {PB1, PB2, PB3, PB4};
  for (uint8_t i = 0; i < 4; i++) {
    bool c = (digitalRead(pins[i]) == LOW);
    if (c && !p[i]) pushMark('1' + i);
    p[i] = c;
  }
  while (out.available()) {
    uint8_t c = out.read();
    if (c >= 32) pushMark(c);
  }

  uint32_t ms = millis();
  if (digitalRead(DIP2) == LOW && (ms - lastHeartbeat) > 1000) {
    lastHeartbeat = ms;
    if (out.availableForWrite() > LINE_MAX) {
      char hb[LINE_MAX];
      int k = snprintf(hb, sizeof(hb),
                       "# hb L=%lu E=%lu ovr=%lu/%lu dropped=%lu depth=%u\n",
                       (unsigned long)tapL.frames, (unsigned long)tapE.frames,
                       (unsigned long)tapL.overruns, (unsigned long)tapE.overruns,
                       (unsigned long)dropped,
                       (unsigned)((r_head - r_tail + RING_SZ) % RING_SZ));
      if (k < 0) k = 0;
      if (k > (int)sizeof(hb) - 1) k = (int)sizeof(hb) - 1;   // snprintf
      out.write((const uint8_t *)hb, k);                      // returns WOULD-be
    }
  }
  if ((ms - lastBlink) > 500) { lastBlink = ms; digitalToggle(BLUE_LED); }
}
