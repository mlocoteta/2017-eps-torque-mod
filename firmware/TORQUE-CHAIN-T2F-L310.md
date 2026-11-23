# `39990-T2F-L310` — LKAS torque chain traced, mapped to the 2020 torque mod

**Date:** 2026-11-23. Ghidra 12.2 headless, gp=`0x03FF8000`. EVIDENCE = decompiled +
constants read from image; BELIEF marked. **This is analysis, not a build proposal** —
modifying any of this is a safety-critical change that would need the kit's full gate /
adversarial / telemetry discipline first.

## The chain (camera serial command → motor)

```
U2 RX ISR ─FUN_00023610─ assemble 4-byte frame @0x3FFED8C
   └─FUN_00023200─ decode 9-bit steer → 0x3FFEC06
        ├─ ×16, DEMAND CLAMP ±3840  [0x27072/74]  = ±240
        ├─ DYNAMIC CLAMP ±(table<<5)  [FUN_0001ecc8 @ptr 0x3FFECE0]
        └─ → 0x3FFED90 (clamped steer) , 0x3FFEC12 (mirror)
   FUN_00023b18  ── THE LKAS PID CONTROLLER ──
        setpoint = interp(map@ptr 0x3FFECB8)         [FUN_0001ecbc + FUN_0001ed0c]
        error    = setpoint − feedback(0x3FFED92) → 0x3FFEC4C   [PID input clamp 0x27036/38]
        P = error·Kp(tbl@0x3FFECC0)>>5   clamp [0x27044/46]  → 0x3FFEC50
        D = Δerror·Kd(tbl@0x3FFECC4)>>5  clamp [0x27040/42]  → 0x3FFEC56
        I = Σ Ki(0x2703A)·error>>10, deadband [0x27048/4A], clamp [0x2703C/3E] → 0x3FFEC52
        sum = P+D+I → 0x3FFEC58                       [sum clamp = hard ±0x7FFF, not a cal]
        × fwd gain(tbl@0x3FFECEC/ECB4) × gain2(tbl@0x3FFECBC) × sign gain[0x27050/51] >>shifts
        OUTPUT CLAMP [0x2704C/4E] ±3840  → 0x3FFEC2A (LKAS torque command)
   FUN_0002395c  ── consumes 0x3FFEC2A → motor-command stage (mix w/ base assist → driver)
```

## Why the command can't exceed ±240 (EVIDENCE)

`±3840` (= ±240 × 16) gates the chain in **three** independent places — the demand clamp
`0x27072/74`, the P-term clamp `0x27044/46`, and the **output clamp `0x2704C/4E`**. The
output clamp is the final gate; nothing downstream of it exceeds ±3840. So raising only
one clamp does nothing — the next one re-limits. Confirmed at instruction level
(`FUN_00023200` 0x232C4–0x232EE; `FUN_00023b18` tail 0x23DC0-ish).

## Stock calibration constants (EVIDENCE, read from image)

| addr | value | role |
|---|---|---|
| `0x27036/38` | ∓3840 | PID input (error pre-scale) clamp |
| `0x2703A` | **0** | Ki — integral DISABLED in stock |
| `0x2703C/3E` | ±256 | I-term clamp |
| `0x27040/42` | ±2560 | D-term clamp |
| `0x27044/46` | ±3840 | P-term clamp |
| `0x27048/4A` | ±128 | I deadband |
| `0x2704C/4E` | **±3840** | **OUTPUT torque clamp** (final gate) |
| `0x27050` / `0x27051` | −32640 / 128 | sign-dependent gain (same/opp sign) |
| `0x27072/74` | **±3840** | **steer DEMAND clamp** (= ±240) |

## 2020 torque mod → 2017 equivalent (the requested mapping)

2020 cells from the V293 torque-mode artifact (`docs/artifacts/v293-torque-mode/`).
Structural/functional equivalents — **not address-portable** (different chip/compile).

| 2020 cell | role | **2017 T2F equivalent** | stock 2017 value |
|---|---|---|---|
| `0xC61B4` | output clamp | **`0x2704C/4E`** | ±3840 |
| `0xC61BC` | P clamp | `0x27044/46` | ±3840 |
| `0xC61B6` | D clamp | `0x27040/42` | ±2560 |
| `0xC61BA` | I clamp | `0x2703C/3E` | ±256 |
| `0xC61BE` | sum clamp | hard ±0x7FFF (not a cal cell) | — |
| `0xC62E6` | fb saturation clamp | `0x27036/38` (PID input clamp) | ±3840 |
| `0xC63E6` | Ki | `0x2703A` | 0 |
| `0xC62E4` | I deadband | `0x27048/4A` | ±128 |
| `0xC6CD0` | forward LKAS gain | fwd-gain tables @ptr `0x3FFECEC`/`ECB4` + sign gain `0x27050/51` | — |
| `MAP_PTR 0xC9A88` | assist/setpoint map | table **`0x28800`** (@ptr `0x3FFECB8`, interp `FUN_0001ed0c`) | — |
| `KP_PTR 0xCB994` | Kp | table **`0x28B00`** (@ptr `0x3FFECC0`) | — |
| `KD_PTR 0xCB7D4` | Kd | table **`0x28C00`** (@ptr `0x3FFECC4`) | — |
| `TAPER_*` ptrs | forward-gain schedules | **`0x28700`** (@`ECB4`), **`0x29450`** (@`ECEC`, LKAS-active), gain2 **`0x28A00`** (@`ECBC`) | — |
| — (2020 has no serial demand) | steer demand clamp | `0x27072/74` | ±240 |
| taper/dynamic | dynamic steer clamp | `FUN_0001ecc8`(table **`0x29150`** @ptr `0x3FFECE0`) | — |
| `0xC674E` | EME soft limit | not yet located | TBD |

All table pointers set in **`FUN_000242cc`** (flash tables `0x27200`–`0x29550`, mostly
256-byte curves). The map/Kp/Kd/gain tables are now resolved to flash; EVIDENCE.

## Speed-scheduled final limiter — `FUN_000238bc`

Downstream of the engage/taper, `0x3FFEC2E` passes one more limiter before the motor:
- clamp to `±0x3FFED1E` (a dynamic cap), then
- **low speed** (`0x3FFEC18 < DAT_27024`): clamp to `±DAT_2706C/6E` = **±3840 (±240)** — the
  second ±3840 pair found in the cal block;
- **higher speed**: clamp to a **speed-scheduled limit** `FUN_0001ecc8(table 0x28600)[speed] << 7`,
  with floor/ceiling `DAT_27068/6A`.
- result → `0x3FFED94`.

So ±240 is enforced in **four** cal sites total (`0x27072/74`, `0x27044/46`, `0x2704C/4E`,
`0x2706C/6E`), and above a speed threshold a **table (`0x28600`) schedules the LKAS torque
limit**. Raising LKAS authority means raising all four ±3840 sites AND the `0x28600` speed
table — on a safety-critical path, behind a flash. The torque-mod lever set is now complete.

## Motor stage — `FUN_0002395c` (engage / rate-limit / taper)

Consumes the PID output `0x3FFEC2A` and produces the final motor torque `0x3FFEC2E`:
- speed-gated engage SM (`sRam03ffd648` speed, `sRam03ffd656` vs `0x27052–0x27060`),
  debounce `0x27062/63` → engaged flag `0x3FFEC2C`.
- engaged: rate-limit — `ec30 += 0x27066` ramp, ceiling = output clamp `0x2704E`, then
  `ec2a` saturated to ±ramp → `0x3FFEC2E`.
- disengaging: taper `0x3FFEC2E` toward 0 / `±0x27064`.

So the final ceiling the motor sees is **min(output clamp `0x2704E`, rate-ramp)** — a
fourth place the ±3840 appears. `0x3FFEC2E` → the base-assist mix / motor driver (next).

## CAN vs serial — is the LKAS command ever CAN (0xE4 / 228)?  (EVIDENCE)

**No active CAN path feeds the LKAS command in this firmware — it is serial/UART only.**
Every controller input is written exclusively by serial-decode functions:
- steer `0x3FFEC06` ← `FUN_00023200` (serial) only
- clamped `0x3FFED90` ← `FUN_00023200`; PID input `0x3FFEC26` ← `FUN_00023eb4` (from `ed90`)
- feedback `0x3FFED92` ← `FUN_00023de8`

The chip **does** have a CAN controller (`C0`, 32 message buffers) — used for vehicle
signals (e.g. the speed `0x3FFD648` the PID schedules on). ⚠ **Correction:** an earlier
16-bit value scan appeared to find `0x00E4` in a "CAN ID table"; that was a FALSE POSITIVE
— the bytes at `0x5BBC`/`0x8C08` are monotonic **lookup-table ramps** (`…e3 e3 e4 e5…`),
not CAN IDs. So there is **no evidence** that CAN `0xE4` STEERING_CONTROL is received here.
Whether a *dormant* (shared-codebase) `0xE4` RX buffer exists is unresolved — it would need
the CAN message-buffer init trace (`C0MCONFxx`/`C0MIDxx`) — but even if present it is **not
wired to the steering controller**. BELIEF: this is a serial-LKAS-only EPS; CAN carries
vehicle data, not the steer command.

Note: the Honda DBC `STEER_TORQUE [-3840|3840]` range **equals** this firmware's internal
clamp — the serial path's `×16` maps the 9-bit wire value into the same torque units.

## Open items (BELIEF / next traces)

1. **Table pointers → flash addresses.** The map/Kp/Kd/gain tables are reached via RAM
   pointers (`0x3FFECB8/CC0/CC4/CE0/CEC/CBC`) set in an init routine. Their actual flash
   addresses (the 256-tables near `0x27200`? the dual bank?) need the pointer-init trace.
   Until then the scalar clamps/gains above are the nailed-down levers; the curves are not.
2. **Plausibility monitors** `FUN_00024760`/`FUN_00024690` debounce the steer command vs
   `0x270BF–0x270C2` and raise faults (`FUN_000245f4(0x39/0x3a)`). ⚠ Raising the ceiling
   could trip these — must be checked before any mod.
3. **`FUN_0002395c`** (motor-command stage) and the base-assist mix / motor driver
   (CSI S1 cluster or FOC/PWM) — the stage after `ec2a`.
4. **Cal redundancy / CRC** for the `0x27036–0x27074` block — is it single-copy or mirrored
   + CRC-checked? (`0x2706C/6E/8C` also hold ±3840.) Must be answered before an edit.

Repro: `ghidra/SetGPDecomp.java 0x3ff8000 <addr>`, `ghidra/FindAccess.java <disp>`.
