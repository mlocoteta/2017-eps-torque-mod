# 2016/2017 Accord LKAS↔EPS serial link — complete byte map

**9600 8E1, two one-way lines, 100.0 Hz.** Camera→EPS 4 bytes, EPS→camera 5 bytes.

**Evidence base:** 39 040 LKAS + 39 037 EPS frames from four of the operator's drives
(normal driving, lane departures, minimal lane departure, general drive), **all
checksum-valid, zero parity errors**, plus 10 215 + 10 215 frames from a capture with
the car in its errored state. Derived from the bytes, never from the fork's C — which
is wrong about motor torque and unaware of six other fields.

---

## Framing invariant

Byte 0 has **top nibble < 4**; every other byte has **top nibble ≥ 4**. This is what
makes resync unambiguous, and it holds in 39 040/39 040 frames. The checksum's
`%128 + 128` exists to guarantee it for the last byte; `bit7 = 1` on bytes 1–3 does the
same job for the rest. **Those high bits are structural, not data.**

---

## Camera → EPS (4 bytes)

```
byte0   bit7   always 0                       reserved
        bit6   always 0                       reserved
        bit5   COUNTER                        toggles EVERY frame (100.0%)
        bit4   always 0                       reserved
        bit3   steer SIGN                     MI 0.98 vs sign(steer)
        bit2:0 steer magnitude [7:5]

byte1   bit7   always 1                       framing
        bit6   always 0                       reserved
        bit5   LKAS ACTIVE                    MI 0.98; flips only 0.1%
        bit4:0 steer magnitude [4:0]          bit0 IS DATA (see below)

byte2   bit7   always 1                       framing
        bit6   = NOT byte1.bit5               100.00% redundant copy of LKAS active
        bit5   LDW intervention WITH steering 3.8%  (0xB0: mean |steer| 101, max 240)
        bit4   LDW detected                   4.2%  (0xD0: LKAS off, |steer| max 0)
        bit3   unknown                        set in 1 frame of 39 040
        bit2   FAULT                          0/39 040 healthy, 10 215/10 215 errored
        bit1   always 0
        bit0   always 0

byte3   checksum = ((256 - (b0+b1+b2)) mod 128) + 128
```

**Steer** is 9-bit two's complement: `sign·256 + magnitude[7:0]`, range −256…+255.
Stock uses **−240…+240**. Observed `byte2` states: `0x80 0xA0 0xB0 0xC0 0xC8 0xD0`.

---

## EPS → camera (5 bytes)

```
byte0   bit7:6 always 0                       reserved
        bit5   COUNTER                        toggles EVERY frame (100.0%)
        bit4   always 0                       reserved
        bit3   driver torque SIGN  (inverted) MI 0.94 vs driver band
        bit2:0 driver torque [7:5] (inverted)

byte1   bit7   always 1                       framing
        bit6   always 0                       reserved
        bit5   LKAS ENGAGED — EPS's OWN VIEW  agrees with the camera 94.19%
        bit4:0 driver torque [4:0] (inverted)

byte2   bit7   always 1                       framing
        bit6   = NOT byte1.bit5               100.00% redundant
        bit5   motor torque SIGN  ─┐
        bit4   motor torque SIGN   ├ ONE sign bit, replicated (sign extension)
        bit3   motor torque SIGN  ─┘ 000 ×20 755, 111 ×18 239, other ×43 (0.11%)
        bit2   LDW acknowledge               echoes camera byte2.bit5 at 99.7%
        bit1   always 0
        bit0   = byte2.bit2                  100.00% duplicate

byte3   bit7   always 1                       framing
        bit6:0 motor torque magnitude (7 bits)

byte4   checksum = ((256 - (b0+b1+b2+b3)) mod 128) + 128
```

**Motor torque** is 8-bit signed: sign from `byte2.bit3`, magnitude from `byte3[6:0]`.
Observed −127…+126, median 0. Validated against the commanded steer at a 3 ms lag:

| subset | r |
|---|---|
| all frames | +0.476 (most motor torque is base driver assist) |
| \|cmd\| ≥ 100 | +0.817 |
| \|cmd\| ≥ 200 (the LDW shake) | **+0.872** |

---

## The three findings that matter

### 1. `byte1.bit5` on the EPS side is an ACKNOWLEDGEMENT

It is not a copy of the camera's request — it agrees only **94.19%**:

- camera asks ON, EPS says OFF: **167 frames**
- camera asks OFF, EPS says ON: 2 100 frames (release lag)
- at engage, the EPS confirms after a **median 12 frames ≈ 120 ms**

Full motor authority only exists while it is set: max \|motor\| **127** when set vs
**84** when clear.

**This is the signal to watch when probing the command ceiling.** If the EPS refuses a
command, this bit is where it says so — not in anything the camera sends.

### 2. `byte2.bit2` camera-side is the fault flag

- healthy: **0 of 39 040** frames
- healthy **with LKAS off**: 0 of 16 608 — so "LKAS disabled" alone does not set it
- errored: **10 215 of 10 215**

⚠ The errored capture is a stationary car, so it is not a perfectly matched control.
The 16 608 healthy-LKAS-off frames are the useful control, and they are clean.
**Status: strong BELIEF, one controlled capture away from EVIDENCE.**

### 3. `byte1.bit0` camera-side is DATA, not a "wiggle"

The fork overwrites it with a forced toggle. Three measurements say it is the real LSB:

- correlation with the frame counter: **49.9%** — exactly chance
- at the ±240 clip the camera dithers 240/239 (`B0`/`AF`), plateaus split ~50/50
- at `steer == 0` it is constant 0 for 17 026 frames and the EPS never complains

The per-frame liveness the EPS likely wants is `byte0.bit5`, which toggles 100% of the
time in both directions regardless of anything else.

---

## What the fork reads, and what it misses

| field | LKAS_EPS_V3 |
|---|---|
| frame structure, checksum, sync | correct |
| steer encode/decode | correct except it destroys `byte1.bit0` |
| driver torque | correct |
| **motor torque** | **sign destroyed — 46.8% of frames are negative, it emits none** |
| EPS LKAS acknowledge (`b1.bit5`) | read into CAN but never acted on |
| LDW bits (camera `b2.5/4`) | masked in one path, hardcoded away in `serialSteerToEPS` |
| LDW acknowledge (EPS `b2.2/0`) | unread |
| fault flag (camera `b2.2`) | unread |
