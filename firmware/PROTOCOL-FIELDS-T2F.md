# `39990-T2F-L310` — complete LKAS↔EPS serial field dictionary

**Date:** 2026-11-23. Every field decoded from the EPS firmware (`FUN_00023610` framing,
`FUN_00023200` RX extract, `FUN_0002338c` TX build). EVIDENCE from decompile unless marked
BELIEF. Link: 9600 **8E1** on UARTA2; camera→EPS = 4 bytes, EPS→camera = 5 bytes; both
checksummed `(256−sum)%128+128` (high bit forced → byte ∈ [0x80,0xFF]).

**Frame sync (both directions):** byte0 has bit7 = 0 (frame start); every later byte has
bit7 = 1. The EPS resyncs on bit7==0.

## CAMERA → EPS  (4 bytes) — the steering command

| byte | bits | field | RAM | meaning |
|---|---|---|---|---|
| **0** | 7 | 0 | — | frame-start marker |
| | 6 | flag | `ec0d` | `byte0 & 0x40` — request/qualifier bit (part of the enable gate) |
| | 5 | counter | — | alternates each frame (liveness) |
| | 3..0 | steer hi | → `ec06` | `steerB1`: **bit3 = sign**, bits2..0 = magnitude[7:5] |
| **1** | 7 | 1 | — | framing |
| | 6 | flag | `ec0a` | `byte1 & 0x40` |
| | 5 | **LKAS ON** | `ec15` | `byte1 & 0x20` — the `0xA0` marker's enable bit |
| | 4..0 | steer lo | → `ec06` | magnitude[4:0] |
| **2** | 7 | 1 | — | framing |
| | 5 | **LKAS active** | `ec0e` | `byte2 & 0x20` |
| | 4..3 | **MODE** | `ec09` | **2-bit mode, valid 0/1/2** — engagement ramp select (see below) |
| **3** | 7..0 | **checksum** | — | `(256−Σbytes0..2)%128 + 128` |

**Steer value (EVIDENCE):** `steer = signext9( (byte0 & 0x0F)<<5 | (byte1 & 0x1F) )` →
9-bit signed, range −256..+255. Internally **×16** (`0x3FFEC06` → `×16`), then clamped to
**±3840 (= ±240)**. So the commandable steer torque is **±240**, in Honda `STEER_TORQUE`
units (the CAN DBC's `[-3840|3840]` range ÷16).

## EPS → CAMERA  (5 bytes) — the status/feedback report

Two measured quantities are packed, plus status bits. Base masks from cal
`0x27004..0x27008` (byte0=`0x00`, bytes1–4=`0x80` → framing bit7). Value1 (reported
torque/measure) is clamped to `±16320` (`0x27000/02`).

| byte | bits | field | source | meaning |
|---|---|---|---|---|
| **0** | 7 | 0 | — | frame-start |
| | 6 | flag | `ec0c` | set while a transient flag is counting down |
| | 5 | counter | `ec16` | toggles each frame (liveness) |
| | 4 | fault | `ed01/ed02` | set on fault |
| | 2..0 | value1[14:11] | `d648`/`d644` | measured torque/signal, high bits |
| **1** | 7 | 1 | — | framing |
| | 6 | flag | `ed77` | |
| | 5 | flag | `ed9e` | (else sets byte2 bit6) |
| | 4..0 | value1[10:6] | | measured torque/signal, low bits (9-bit field total) |
| **2** | 7 | 1 | — | framing |
| | 2..0 | value2[15:13] + **status code** | `ed92` + state | motor-torque/feedback high bits; low bits also encode EPS state code (3/4/6 = modes) |
| **3** | 7..0 | value2[12:6] | `ed92` | feedback/motor torque, mid bits |
| **4** | 7..0 | **checksum** | — | same formula |

(The two reported quantities match the fork model's "driver/measured torque" and "motor
torque" fields; exact scaling of value1 vs value2 is BELIEF pending bench correlation.)

## The MODE field (`byte2` bits 4:3) — NOT a torque/angle mode

`FUN_00023200` stores it to `0x3FFEC09` (only 0/1/2 accepted). Consumers:
- `FUN_000237a0` (engagement ramp): **mode 2** uses **dynamic** ramp-in/out rates
  (`ecdc`/`ecde`); **modes 0/1** use **fixed** cal rates (`0x27070`=2, `0x27071`=1).
- `FUN_0002533c`: just reports `mode == 1`.

⇒ **The mode bits select how fast assist ramps in/out, not the torque magnitude.** It is an
engagement-smoothness selector, not a higher-authority mode and not an angle mode.

### What each byte2 control bit actually does (EVIDENCE)

- **bit5 — LKAS active (`ec0e`)**: the real "steer now" enable. In the PID (`FUN_00023b18`)
  it **selects the forward-gain table** — active → gain table `0x29450`, inactive → `0x28700`
  — and gates the torque output. This is the bit that turns steering assist on.
- **bits4:3 — the 2-bit field (`ec09`, = what the fork model called the "LDW"/mode bits)**:
  an **engagement-state command** from the camera, consumed two ways:
  - `FUN_000237a0` (ramp): **mode 2** → fast/dynamic ramp rates from cal `0x29130`/`0x29140`;
    **modes 0/1** → the slow fixed rates `0x27070`(=2)/`0x27071`(=1).
  - `FUN_000255b8` (engage arbiter): **mode == 1** is one of several OR'd **transition
    triggers** — i.e. mode 1 forces an engage/disengage transition rather than steady steer.
  So: **0 = normal steady engagement, 1 = transition/hold request, 2 = fast-ramp engagement.**
- **bit6 (`byte2 & 0x40`)**: in stock this is the **inverse of LKAS-ON** (a redundant
  plausibility/HUD bit) — the EPS control path does not read it for steering. BELIEF (matches
  the fork conformance observation "byte2 bit6 == NOT lkasOn").

None of these change the ±240 clamps — they control **on/off, ramp speed, and engagement
transitions**, plus which forward-gain *table* is used (both tables still feed the same
clamps). "LDW" in the fork model = this byte2 engagement field; the EPS treats it as an
engagement/mode command, not a separate lane-departure actuator.

## Is there a hidden higher-torque or torque/angle mode? — NO (EVIDENCE)

- **Torque, not angle.** The command is always a torque request (steer field → PID
  setpoint). There is no angle-control path; no mode reinterprets the field as an angle.
- **±240 is absolute in every mode and at every speed.** The ceiling is enforced by the
  **output clamp `0x2704C/4E` = ±3840 unconditionally**, plus the demand clamp `0x27072/74`,
  the P-term clamp `0x27044/46`, and the speed-scheduled limiter `0x2706C/6E` whose table
  `0x28600` is a **flat `0x1E` (30 → 30<<7 = 3840 = ±240) at all speeds**. No mode, speed, or
  camera bit selects a different (higher) clamp or a different clamp source.
- **No variant/market unlock.** The dual cal banks are byte-identical; no config byte
  switches to a higher-authority profile in the mapped control path.
- The only "mode-like" authority change is the engagement ramp (mode 2, dynamic rates) and
  the speed-scheduled limiter — both bounded by the same ±240 ceiling.

⇒ Raising torque authority is **not** reachable by any command, mode, or diagnostic — only by
changing the cal clamps in flash (see `TORQUE-CHAIN` / `FINDINGS-SUMMARY`). The K-line
diagnostic "unlock" (`0xC2 06 C7`) enables extended *diagnostics*, not higher torque.
