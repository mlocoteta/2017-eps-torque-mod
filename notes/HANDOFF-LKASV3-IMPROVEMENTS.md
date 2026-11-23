# Handoff — improving the LKAS_EPS_V3 board firmware (2016/2017 Honda Accord)

**For:** an engineer or agent modifying `LKAS_EPS_V3`, the STM32F103 board that sits
between the Honda Sensing camera and the EPS on a 2016/2017 Accord.
**Date:** 2026-11-13. **Author:** prior analysis session, from on-car captures.

You do not need prior context. Everything below was re-derived from captured bytes.
**Do not trust the existing C comments** — several are wrong, and they are the reason
some of these defects exist.

---

## 1. Safety constraints — read before changing anything

This firmware sits inline on a live steering link in a **daily-driven car**. There is
no spare EPS unit.

1. **Pass-through must never stall.** The camera and EPS exchange a frame every 10 ms;
   the production firmware treats >50 ms of silence as a fault. Any new code in the
   receive path must be non-blocking. Do not add `delay()`, and do not add a blocking
   print between receiving a byte and relaying it.
2. **This board can command steering torque.** It is not a passive device. Changes that
   alter magnitude, rate or engagement state change what the car physically does.
3. **Never flash mid-drive.** The board stops relaying while programming.
4. The separate read-only logger (`analysis-2017accord/teensy_logger/`, a Teensy 4.0)
   is the safe way to gather more data. It only relays and records.

---

## 2. Evidence base

All findings below come from these captures, decoded offline:

| capture | frames | state |
|---|---|---|
| 4 drives in `Logs/` (normal driving, lanedepart, minimallanedepart, generaldrive) | **39 040 LKAS + 39 037 EPS** | healthy, includes real lane departures |
| `2026-11-13_002058_base.csv` | 10 215 + 10 215 | car in its errored state, stationary |

**All checksum-valid. Zero checksum failures. Zero parity errors.** 9600 8E1, 100.0 Hz.

---

## 3. Where the files are

Repo root: `C:\Users\mloco\EPS Torque\accord-eps-torque-mod`

| what | path |
|---|---|
| **Full byte map — read this first** | `analysis-2017accord/notes/BYTE-MAP-2017-accord-lkas-eps.md` |
| Byte-exact protocol model (Python) | `analysis-2017accord/model/honda_serial_model.py` |
| Earlier findings, incl. the ~230 ceiling | `analysis-2017accord/notes/FINDINGS-2026-11-12-protocol-and-230.md` |
| Fork source (archived copy, pinned) | `analysis-2017accord/reference/upstream/LKAS_EPS_V3/` |
| Upstream provenance + commit hashes | `analysis-2017accord/reference/upstream/PROVENANCE.md` |
| Drive logs | `Logs/*.csv` |
| Log decoder (auto-reassembles split frames) | `analysis-2017accord/model/decode_tap_csv.py` |
| Re-framer | `analysis-2017accord/model/reframe_tap.py` |
| Stock-vs-fork comparison | `analysis-2017accord/model/compare_v3_fork.py` |
| Bit-level census | `analysis-2017accord/model/byte_map.py` |
| Read-only logger firmware | `analysis-2017accord/teensy_logger/` |
| Portable logger for a car laptop | `analysis-2017accord/portable_logger/` |

Live fork repo: `https://github.com/mlocoteta/LKAS_EPS_V3` (archived at `ac40e476`).

Python: run with the repo root as CWD. Only dependency is `pyserial` (logger only);
the analysis scripts are pure stdlib.

---

## 4. Defects, in priority order

### P1 — motor torque sign is destroyed
`src/canMessages.cpp:72-78`, `txMotorTorque()`

```c
uint16_t motorTorque  = (status->epsData[2] & B00110000) << 4;
         motorTorque |= (status->epsData[2] & B00001000) << 4;
         motorTorque |= (status->epsData[3] & B01111111);
if (motorTorque & 0x0200) motorTorque = ~(abs(motorTorque)) & 0x01FF;
```

`epsData[2]` bits 5, 4 and 3 are **one sign bit, replicated** (sign extension) —
measured `000` ×20 755, `111` ×18 239, anything else ×43 (0.11% of 39 037 frames).
This code spreads that single bit across three *magnitude* positions, then "corrects"
with `~x & 0x1FF`, which cannot produce a negative value.

Measured consequence: **46.8% of frames are genuinely negative; the fork emits zero.**
Output range `0..265` instead of `-127..+126`. Correlation with commanded steer during
a lane-departure event: **+0.110** (fork) vs **+0.872** (correct). It is accidentally
correct for positive torque, which is why it half-works.

```c
int16_t calculateMotorTorque(uint8_t b2, uint8_t b3) {
    int16_t mag = b3 & 0x7F;
    return ((b2 >> 3) & 1) ? (mag - 128) : mag;   // b2 bit3 = sign
}
```

### P2 — the camera's byte 2 is parsed into nothing
`src/hondaSerial.cpp`, `deconstructLKAS()` — `case 2:` is **empty**.

`ldw_enable` (`include/hondaSerial.h:26`) is declared but **never assigned anywhere in
the codebase**. So at `src/hondaSerial.cpp:90`:

```c
msg[2] = 0x80;
msg[2] |= lkasMsg->ldw_enable;   // always 0 -> msg[2] is always exactly 0x80
```

Byte 2 carries six distinct states in stock traffic and three live fields:

| bit | meaning | rate |
|---|---|---|
| 6 | `NOT` LKAS-active — a **100.00% exact inverse** of `byte1.bit5` | 42.5% |
| 5 | LDW intervention **with** steering (`0xB0`: mean \|steer\| 101, max 240) | 3.8% |
| 4 | LDW detected (`0xD0`: LKAS off, \|steer\| exactly 0) | 4.2% |
| 2 | **fault** — 0/39 040 healthy, 10 215/10 215 errored | — |

Populate `case 2:` and carry these through.

### P3 — `byte1.bit0` is data, not a "wiggle"
`src/hondaSerial.cpp:82-83`

```c
steerB0 = steerB0 & B00011110;
steerB0 = steerB0 | ((lkasMsg->steerLSB ^ 1) & B00000001);  // "Without this the EPS will error out"
```

The comment is wrong. Three independent measurements say bit0 is the real LSB:

- correlation with the frame counter: **49.9%** — exactly chance
- at the ±240 clip the camera dithers 240/239 (`B0`/`AF`); plateaus split ~50/50
- at `steer == 0` it is constant 0 for **17 026 consecutive frames** and the EPS never
  complains

Cost: half the command resolution — 512 distinct commands collapse to 257. The
per-frame liveness the EPS more likely wants is `byte0.bit5`, which toggles 100% of the
time in both directions unconditionally.

⚠ The original author observed a real fault without this. Do not simply delete it —
change it, log, and verify `EPS byte1.bit5` (see §5) stays set.

### P4 — `steerMax 239` is one below stock
`include/common.h:17`. Stock reaches **±240** (580 frames at 240, 508 at 239). With the
P3 toggle also forcing even values, the fork cannot reach what the car itself commands.
The wire field is 9-bit two's complement, so **−256…+255** is representable; everything
up to 255 encodes cleanly and keeps the framing invariant. **Whether the EPS honours
above 240 is untested — nobody has ever sent it.**

### P5 — rate limit is below stock behaviour
`include/common.h:19-20`, `steerDeltaUp/Down = 100`. Measured frame-to-frame deltas:
median 1, p99 96, **max 479**. 208 frames (0.53%) exceed 100; the extremes are
full-scale reversals `-239 → +240` during the lane-departure shake.

### P6 — `int8_t` truncation in `torque_blend`
`src/canMessages.cpp:321`: `int8_t driver_torque = driverTorque >> 1;`

`driverTorque` comes from `calculateSteerTorque()` and is **always `[0,511]`**, never
negative. Measured: min 0, median 474, max 511 — the full range is used. **64% of
frames have raw ≥ 256**, so `driver_torque` is negative as an `int8_t` most of the
time. The sign flip is real; where it lands physically needs a capture with the wheel
loaded. Do not assume the published scaling is correct.

---

## 5. ⭐ The most useful thing found — use this as your instrument

**`EPS byte1.bit5` is an ACKNOWLEDGEMENT, not an echo.**

It agrees with the camera's request only **94.19%**:

- camera asks ON, EPS says OFF: **167 frames**
- camera asks OFF, EPS says ON: 2 100 frames (release lag)
- at engage, the EPS confirms after a median **12 frames ≈ 120 ms**
- authority follows it: max \|motor torque\| **127** when set vs **84** when clear

**This is where the EPS tells you it refused a command.** The board currently reads it
into CAN but never acts on it.

Any experiment that probes the command ceiling should watch this bit rather than rely
on how the car feels.

---

## 6. Do NOT "fix" these — they are correct

- Frame structure (4 bytes out, 5 back), sync rule (top nibble < 4), and the checksum
  `(256 - sum) % 128 + 128`. **Zero failures in ~78 000 frames.** The `%128 + 128` is
  load-bearing: it keeps the checksum ≥ 0x80 so it can never be mistaken for a frame
  start.
- 9600 **8E1**.
- The 9-bit sign+magnitude steer field split across `b0[3:0]` / `b1[4:0]`.
- `calculateSteerTorque()` (driver torque) — correct.
- `verifyCounter()`'s mod-4 arithmetic. The **serial** counter is mod 2, but this
  function is only ever applied to the **CAN** counter, which is mod 4. Correct as
  written. (This was nearly "fixed" into a bug.)
- `steerDeltaUp/Down = 100` as a *nominal* value — it matches the camera's own ~100/frame
  slew during interventions. Only the extremes exceed it (see P5).
- The 5-frame zero lead-in on engage — stock sends 3–12 zeros, clustering at 4–5.

---

## 7. Open questions — do not assume answers

1. **Is there a command ceiling above 240, and is it a magnitude limit at all?** The
   operator reports the fork erroring around ~230, yet stock sails to 240 with the same
   framing. The differences between fork and stock are now measured and **none of them
   is magnitude** (P2, P3, P5). It may be a protocol-conformance rejection, not a
   torque limit. Test by making the fork byte-for-byte stock-shaped first, then walking
   magnitude up while watching `EPS byte1.bit5`.
2. **The fault flag is strong BELIEF, not EVIDENCE.** The errored capture is a
   *stationary* car, so it is not a matched control. What supports it: 16 608 healthy
   frames with LKAS off, bit2 clear in every one — so "LKAS disabled" alone does not
   set it. A capture of the error while moving would close this.
3. `camera byte2.bit3` was set in exactly **1 frame of 39 040**. Unidentified.
4. The redundant pairs (`camera byte2.bit6` = `NOT byte1.bit5`, 100.00%;
   `EPS byte2.bit0` = `byte2.bit2`, 100.00%) may be validated by the EPS. The fork
   computes `byte1` and `byte2` independently and can emit contradictory pairs that
   stock never produces. **Untested, and a plausible cause of rejection.**
5. Physical units. Nothing maps counts to Nm. ±240 is a number on a wire; what torque
   the EPS delivers for it is set by maps and clamps inside the EPS firmware, which has
   not been read.

---

## 8. Suggested order of work

1. Fix P1 (motor torque sign). Self-contained, no behaviour change on the car, and it
   restores a feedback signal openpilot currently receives backwards half the time.
2. Fix P2 (`case 2:`), carrying byte 2 through faithfully. Also no magnitude change.
3. Surface `EPS byte1.bit5` as an explicit reject/accept signal before any experiment.
4. Only then touch P3/P4/P5, one at a time, each with a logged drive.

Steps 1–3 change no commanded torque and are the right first commit.
