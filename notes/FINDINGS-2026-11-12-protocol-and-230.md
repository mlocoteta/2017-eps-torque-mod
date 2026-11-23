# 2017 Accord LKAS↔EPS serial link — first pass

**Date:** 2026-11-12. **Sources:** operator's `LKAS_EPS_V3` (STM32, production),
`serialSteeringHardware` (boards + V1 Teensy sketch), `reddn/AccordManualSteering`
(Teensy 4.0 + **six stock captures, 20 124 frames**), `reddn/AccordLinDataReader`.

Mirror: `analysis-2017accord/model/honda_serial_model.py`. Everything below was
re-derived from source or from the captures, never assumed.

---

## 1. The wire format — EVIDENCE

9600 **8E1**, two independent one-way lines. Camera→EPS 4 bytes; EPS→camera 5 bytes.

```
LKAS -> EPS                        bit7 .. bit0
  B0   [ 0 ][ 0 ][cnt][ 0 ][sign][ m7 ][ m6 ][ m5 ]      cnt alternates 0/1
  B1   [ 1 ][ 0 ][ on][ m4 ][ m3 ][ m2 ][ m1 ][ m0 ]      0xA0 base, bit5 = LKAS on
  B2   [ 1 ][ x ][ldw][ldw][ 0 ][ 0 ][ 0 ][ 0 ]           0x80 / 0xC0 observed only
  B3   checksum = ((256 - (B0+B1+B2)) mod 128) + 128
```

Steer is a **9-bit two's-complement** field: `sign·256 + m[7:0]`, range −256..+255.

**Framing invariant (EVIDENCE, 20 124/20 124 frames, 0 violations):** byte 0 has
top nibble < 4; every other byte has top nibble ≥ 4. The checksum's `%128 + 128`
is what guarantees the checksum byte can never be mistaken for a frame start.
That is a deliberate protocol design feature, not an accident of the C.

**Checksum: 0 failures in 20 124 stock frames.** The `chksm()` implementation is
correct, including the `uint8_t` wrap, because `(256−tot) mod 128 == (−sum) mod 128`.

---

## 2. What the STOCK camera actually commands — EVIDENCE

Across all six captures:

| band | frames | byte2 | lkasOn |
|---|---|---|---|
| 0 | 5 951 | 0x80 ×455, **0xC0 ×5 496** | 455 |
| 1..100 | 13 054 | 0x80 | all |
| 101..158 | 696 | 0x80 | all |
| **159/160** | **225** | 0x80 | all |
| 161..238 | 16 | 0x80 | all |
| **239/240** | **182** | 0x80 | all |

Two sustained plateaus — **±160** (normal lane keep) and **±240** (lane-departure
intervention; present only in the two "lane departure at end" logs). Each plateau
shows as a *pair* of adjacent values because of the wiggle bit (§3). The 16 frames
between them are the ramp.

**The ramp into 240 is not a ramp.** Frame-by-frame:

```
... 133  135  138   →   240  239  240  239  240 ... (×11)  →  195  99  3  92 ...
```

**138 → 240 in a single 10 ms frame.** The camera does not rate-limit, and the
EPS accepted it.

---

## 3. Bit 0 of the magnitude is not data — EVIDENCE

`hondaSerial.cpp:serialSteerToEPS`:

```c
steerB0 = steerB0 & 0b00011110;                  // keep bits [4:1]
steerB0 = steerB0 | ((steerLSB ^ 1) & 0b1);      // bit0 := inverse of last frame
```

The C comment says the EPS errors out without this "wiggle". The stock captures
confirm the camera does the same thing — that is why every plateau appears as
`159/160` and `239/240` rather than a single value.

**Consequence:** commandable resolution is sign + **7** magnitude bits, not 9.
512 distinct openpilot commands collapse to **257** distinct delivered pairs.
Commanding 230 and 231 are the same command.

---

## 4. The "~230 errors" ceiling — three hypotheses, one refuted

**REFUTED: "the EPS clamps magnitude near 230."** Stock reaches **240** with
`byte2 = 0x80`, `lkasOn = 1` — byte-for-byte the same framing the fork already
sends — and holds it for 11 consecutive frames. No flag is raised to unlock it;
`ldw` bits 5:4 of byte 2 are **never set** in any capture. The EPS accepts 240.

**Still open, in order of my confidence:**

1. **BELIEF — a driver-torque / LKAS-command interlock, not a magnitude limit.**
   At the 240 plateau the EPS-reported driver signal reads 445–478 (raw scale
   0..511). `common.h` already carries `steerThreshold 30` with the comment
   *"prevent driver steer > some value while LKAS is on to prevent LKAS fault"*.
   If the fault is a *product* of command and driver torque, the ceiling would
   move with how hard the wheel is held — which is exactly what "~230" (a soft,
   approximate number) sounds like.
2. **BELIEF — a latching fault, not an instantaneous one.** `AccordManualSteering/notes`:
   *"hitting the brake while continuing to send LKAS torque commands will cause
   the EPS to error (no error displayed) and will not apply any torque until you
   restart the car."* A latching trip means the number you observe is where you
   *noticed*, not where it tripped.
3. **BELIEF — duration, not amplitude.** Stock holds 240 for ~11 frames (110 ms)
   and then backs off hard. A dwell limit would read as an amplitude limit if you
   ramp slowly.

**All three are distinguishable from one logged drive**, and none requires a
firmware image. That is why the logger comes before the firmware.

---

## 5. Defects found in `LKAS_EPS_V3` — EVIDENCE

| # | severity | where | issue |
|---|---|---|---|
| 1 | **instrumentation** | `hondaSerial.cpp:LKAStoEPS` | `status->lkasData[]` is written **only on the passthrough branch**. While manipulating, the transmitted frame goes to a local static, so CAN 523 reports stale bytes. *You cannot see what you sent at the moment it mattered.* |
| 2 | **instrumentation** | same | the camera's original command is never forwarded to CAN, so stock-vs-commanded can't be compared on the same frame |
| 3 | memory | `deconstructLKAS` | `data[5]` indexed by an **unbounded** `totalCounter`; one glitched byte with top nibble ≥ 4 and it walks off the struct |
| 4 | memory | `canMessages.cpp:txRawEPSData` | reads `status->epsData[5]` from a `uint8_t[5]` — OOB |
| 5 | **logic** | `canMessages.cpp:torque_blend` | `int8_t driver_torque = driverTorque >> 1;` — the driver signal is `[0,511]` centred near 256, so `>>1 = 128` → **int8_t −128** at rest. Modelled: `max_steer_allowed` collapses to **0 for every driver value from 100 to 510**. Blending zeroes the command unless `torqueBlendDisable` is set. |
| 6 | range | `common.h` | `steerMax 239` is *below* the 240 stock uses, and the wiggle makes 239 deliver 238/239 |

Defect 5 is modelled in `honda_serial_model.py` §3 of `__main__`; run it.

---

## 6. Next

`analysis-2017accord/teensy_logger/` — passive tap, Teensy 4.0, 9600 8E1,
pass-through first and unconditional, µs timestamps, frame gaps, parity/overrun
counters, button marks. Decode with `model/decode_tap_csv.py`.

Firmware acquisition is **not** on the critical path yet and is hard-gated on a
spare EPS unit regardless (daily driver only; the 2020 program bricked three ECUs).
