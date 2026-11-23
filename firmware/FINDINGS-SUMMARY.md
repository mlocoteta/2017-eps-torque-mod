# 2017 Accord EPS (T2F) — complete findings

**Date:** 2026-11-23. Master consolidation of the `39990-T2F-L310` reverse-engineering.
Every decision-bearing line is EVIDENCE (decompiled / read from the image) or BELIEF
(inference). Firmware binaries are not committed (Honda-copyrighted). This is analysis /
feasibility only — no modified build has been produced or flashed.

---

## 1. Target & how we got the image

- **Car/part:** 2017 Honda Accord (9th-gen), EPS `39990-T2F-L310`.
- **MCU:** Renesas **µPD70F3413, V850E/PG2**, 240 KB code flash (`0x0–0x3BFFF`), RAM base
  **`0x03FF8000`** (from the Renesas device file `DF3413.800`).
- **No chip dump.** The plain image was decoded from the **dealer `.rwd`** container:
  x31 format, cipher `plain = ((cipher − 0x9e) ^ 0x10) + 0xbf`, key `BF109E`. The firmware's
  own part string `39990-T2F-L310` confirms the decode. Ghidra: load flat at `0x0`, V850,
  **gp = `0x03FF8000`** (the reset gp-load is in the boot block, so it must be set manually).
- **The `.rwd` omits `0x0–0x17FF`** (boot sector + reset/interrupt vectors) and some erased
  regions — it carries only the reprogrammed application blocks (85.8 % of flash).

## 2. How the 2017 differs from the 2020 (TVA)

| | 2020 (TVA, V850E2) | **2017 (T2F, V850E/PG2)** |
|---|---|---|
| LKAS command transport | CAN `STEERING_CONTROL` 0xE4 | **Serial UART**, camera↔EPS, 9600 **8E1** (UARTA2) |
| Diagnostics / reflash | CAN **UDS** (0x10/0x27/0x34) | **K-line**, Honda-proprietary (`0xC0–0xC7`) |
| SecurityAccess | firmware consts @`0x92C0` | bootloader-resident (not in image) |
| Torque controller | LKAS rate PID | **same PID structure**, different addresses |

Same torque units: the Honda DBC `STEER_TORQUE [-3840|3840]` equals this firmware's internal
±3840 clamp; the serial path's `×16` maps the 9-bit wire value into that space.

## 3. Serial LKAS protocol (EVIDENCE, byte-exact from the EPS side)

- **Camera = UARTA2.** Init `FUN_00020024`: `U2CTL0=0x1E` (LSB-first, even parity, 8-bit,
  1 stop = 8E1), baud `U2CTL2=0xCD`. UART registers `0xFFFFFA20` block.
- **RX (camera→EPS, 4 bytes):** `FUN_00023610` assembles by frame-sync bit — byte0 has
  bit7=0 (frame start), bytes 1-3 bit7=1 — into buffer `0x3FFED8C`; on the 4th byte calls
  `FUN_00023200` (decode) then `FUN_0002338c` (build response).
- **Steer decode** (`FUN_00023200`): `(byte0 & 0x0F)<<5 | (byte1 & 0x1F)` → 9-bit signed
  (sign at bit 8, sign-extended) → `0x3FFEC06`.
- **TX (EPS→camera, 5 bytes):** `FUN_0002338c` builds 4 data bytes + checksum via the 5-byte
  sender `FUN_0001ff28` → `U2TX`.
- **Checksum** (`~sum + 1 & 0x7f | 0x80`) = `(256 − sum) % 128 + 128` — matches the fork's
  model exactly, confirmed from firmware.

## 4. The LKAS torque chain (serial command → motor)

```
U2 RX → decode 9-bit steer (0x3FFEC06)
  → DEMAND clamp ±240            [0x27072/74, ×16=±3840]   FUN_00023200
  → dynamic clamp ±(table<<5)    [FUN_0001ecc8 @ 0x29150]
  → FUN_00023b18 = LKAS PID:
       setpoint = interp(assist map 0x28800)
       error = setpoint − feedback(0x3FFED92)
       P = err·Kp(0x28B00)>>5   clamp [0x27044/46]
       D = Δerr·Kd(0x28C00)>>5  clamp [0x27040/42]
       I = ΣKi(0x2703A)·err>>10 deadband[0x27048/4A] clamp[0x2703C/3E]   (Ki=0 stock)
       sum·fwd_gain(0x28700/0x29450)·sign_gain(0x27050/51)
  → OUTPUT clamp ±3840           [0x2704C/4E]
  → FUN_0002395c engage/rate-limit/taper (step 0x27066, taper 0x27064) → 0x3FFEC2E
  → FUN_000238bc speed-scheduled limiter:
       low speed: ±3840          [0x2706C/6E]
       high speed: table(0x28600)<<7, bounds 0x27068/6A
  → 0x3FFED94 → base-assist mix / motor driver (FOC — not yet mapped)
```

## 5. Why ±240 — and the complete torque-mod lever set

**±240 (= ±3840 internal, ×16) is enforced at FOUR cal sites plus a speed table.** No single
edit raises authority; each downstream clamp re-limits.

| lever | address | stock |
|---|---|---|
| demand clamp | `0x27072/74` | ±3840 |
| P-term clamp | `0x27044/46` | ±3840 |
| output clamp | `0x2704C/4E` | ±3840 |
| speed-gated limit (low speed) | `0x2706C/6E` | ±3840 |
| speed-gated limit (table) | `0x28600` | curve |
| D-term clamp | `0x27040/42` | ±2560 |
| I-term clamp / Ki / deadband | `0x2703C/3E` / `0x2703A` / `0x27048/4A` | ±256 / 0 / ±128 |
| assist map / Kp / Kd | `0x28800` / `0x28B00` / `0x28C00` | curves |
| fwd gain / sign gain | `0x28700`,`0x29450` / `0x27050/51` | — |

To raise LKAS authority: raise all four ±3840 sites + the `0x28600` speed table (and re-CRC
the dual bank). This is a **flash-only, safety-critical** change.

**These are the same levers the 2020 Accord "proper torque mod" needed — one-to-one by
function, at 2017 addresses.** The 2020 mod (V293 torque-mode) tuned the output/P/D/sum/I
clamps, the forward LKAS gain, Ki, and the assist/Kp/Kd maps; the 2017 has every one of those
(output `0x2704C/4E`, P `0x27044/46`, D `0x27040/42`, I `0x2703C/3E`, Ki `0x2703A`, gains
`0x28700`/`0x29450`+`0x27050/51`, maps `0x28800`/`0x28B00`/`0x28C00`). The 2017 adds two
serial-platform extras the 2020 (CAN) doesn't have: the **±240 demand clamp** `0x27072/74`
and the **speed-scheduled final limiter** `0x2706C/6E` + table `0x28600`. Full 2020↔2017
correspondence table in `GAP-2020-vs-2017.md`. The difference is transport and addresses, not
the control concept — the torque mod is the same mod on a different chip.

## 6. Calibration storage

- **Dual redundant cal bank** (byte-identical): Bank A `0x02F100–0x031F4E`,
  Bank B `0x031F00–0x034D4E` (`0x2E00` apart). Any cal edit must change **both** + the CRC.
- Scalar clamp/gain cells live near `0x27036–0x27074`; map/Kp/Kd/gain tables `0x27200–0x29550`
  (pointer-initialised in `FUN_000242cc`).

## 7. K-line diagnostics (no reflash) — and PERSISTENCE

Diagnostics run over **UART U1**, Honda-proprietary, length-prefixed; dispatcher
`FUN_0001da3c` on command byte; checksum `~sum+1`.

| capability | command | security | **persistence** |
|---|---|---|---|
| **Live telemetry** (~75×16-bit channels, table `0x8EFC`) | `C0 05 <idx> <cnt>` | none | read-only |
| Read ECU IDs/serials | `0xC5` | none | read-only |
| Actuator self-test (canned pattern) | `0xC2 06 A3/A4` | session unlock | **volatile** — RAM overrides (`0x3FFDCBA…`), cleared at reset/session end; redone every time |
| Bounded parameter write | `0xC2 06 03/08` | gated | **persistent** — commits to EEPROM/data-flash |
| "Unlock" (enables extended diag) | `0xC2 06 C7 01` | — | **volatile** — session flag (`0x3FFD438&8`), re-sent each session |

**Persistence detail (EVIDENCE):** the parameter-write path sets a mailbox bit (`0x3FFCD54`)
consumed by `FUN_00011ffc` → `FUN_000111a8` stages a RAM block → `FUN_00011ce4` commits it to
EEPROM/data-flash with a **read-verify-write** (`FUN_0001f60c` read page, compare, `FUN_0001f5e4`
write if changed). So those writes **survive power cycles**. BUT they are **service/coding
values** (sensor zero, variant coding class), **not** the torque-ceiling cells — those are in
main code flash and unreachable by any K-line command.

⇒ **Answer to "is the no-reflash option permanent or every-time":** it depends which:
- The **persistent** one (EEPROM parameter write) is *write-once, survives restarts* — but it
  **cannot change torque authority**.
- The **volatile** ones (actuator test, session unlock) must be **re-done every ignition /
  session** and only apply while connected in that mode.
- There is **no** no-reflash way — persistent or temporary — to raise the ±240 ceiling.

## 7b. Where each value lives — persistent vs RAM vs flash (EVIDENCE)

| tier | where | how to change | holds | torque-relevant? |
|---|---|---|---|---|
| **Code flash** `0x0–0x3BFFF` | internal flash | **reflash only** (boot mode / K-line bootloader) | **all torque cals** — clamps `0x27036–0x27074`, ramp rates `0x27070/71` + `0x29130/40`, maps `0x28600/700/800/B00/C00`/`0x29150/450`, frame masks `0x27000–08`, dual bank `0x2F100`/`0x31F00` | ✅ **yes — the ceiling lives here** |
| **EEPROM / data-flash** (persistent working set ≈ `0x3FFD8BC–0x3FFDA78` + config flags e.g. direction `0x3FFD886`) | NVM, mirrored to RAM; committed by `FUN_00011ce4` read-verify-write | K-line `0xC2 06 03/08` service write (bounded, gated) | **survives power cycle** — serials (`0x3FFDA58`), sensor-zero / variant-coding | ❌ service/coding only; torque chain reads a couple config flags (direction) but **not** the clamps/gains |
| **RAM** (control working set `0x3FFEC00–0x3FFED9x`; diag buffers; actuator overrides `0x3FFDCBA–CCA`; session/engage flags; report-select `0x3FFD88C`) | internal RAM | recomputed every tick; actuator overrides live-writable via `0xC2 … A4` **in test mode** | **lost at power-off / reset** — redone every ignition | ❌ live-modifiable (test overrides) but volatile; not the ceiling |

**So, to your question directly:** the only values you can modify **persistently without a
reflash** are the EEPROM service/coding values (`0x3FFD8BC–0x3FFDA78`) — and none set the
torque ceiling. The only values you can modify **live** are RAM (actuator-test overrides),
which reset every power cycle. The torque-ceiling cals are in **code flash** — reflash-only,
and a reflash is the sole *permanent* way to change them.

## 7c. Low-speed engage gate (the ~5 km/h / 3 mph cutoff)

`FUN_00025348` (an engage-arbiter trigger) **disengages LKAS when vehicle speed drops below
`DAT_270ED = 5`** (a `u8` km/h value, compared against speed `0x3FFD63A`), with re-engage
hysteresis `DAT_270EE = 2`. This is the ~5 km/h (3 mph) cutoff. EVIDENCE.

- **To allow steering to 0 mph:** set **`0x270ED = 0`** (and `0x270EE` to taste). Code-flash
  cal (same `0x27xxx` block as the torque clamps; single copy — not in the dual bank — but
  the image/`.rwd` CRC still applies) ⇒ reflash to change.
- **No low-speed torque taper:** the dynamic clamp table `0x29150` and the speed-schedule
  table `0x28600` are flat (±3840 = ±240) at all speeds, so full authority is available down
  to 0 — lowering the gate gives real assist at parking speed, not a trickle.
- Caveats: the camera/openpilot side typically has its own min-steer-speed too (must command
  below 5 km/h for anything to happen); other arbiter triggers (driver-override envelope
  `FUN_00025410`, faults `FUN_0002539c`) still apply but are not speed gates. Steering at
  0 mph with full authority is a real behavioral change — bench-validate first.

## 8. Reflash routes

- **CAN: NOT supported** (EVIDENCE: no UDS-over-CAN addressing `0x18DA/0x18DB` in the image;
  CAN only *receives* vehicle signals, e.g. speed `FUN_0001a5e8 → 0x3FFD648`).
- **Honda K-line** (dealer/iHDS): app → bootloader; the reflash **SecurityAccess + flash-write
  are bootloader-resident** in `0x0–0x17FF` — **not in this image**; can't be reversed without
  the boot block.
- ⭐ **Renesas serial boot mode (FLMD0)** — the chip's native programmer, bench only, bypasses
  Honda entirely. See §9.
- **flashPRO / hardware programmer** — same boot interface, vendor tooling.

## 9. Bench reflash procedure (Renesas boot mode) — reference

For the spare bench EPS, to ever flash a modified cal. Reference-level; use
`gregjhogan/renesas-bootmode`'s own V850 wiring diagram for the physical hookup (the kit does
not reproduce wiring — see `notes/REF-dump-tooling-and-chip.md`).

1. **Enter boot mode:** the µPD70F3413 boot ROM supports serial programming, entered via the
   **FLMD0** pin + **RESET** with a UART (TX/RX), 5 V part. (Same entry used to *dump*.)
2. **Check flash security first:** read the chip's security/protection setting in boot mode.
   If write/erase or boot-block protection is set, bench write may be blocked — stop and
   reassess. (BELIEF: unknown until read on the actual unit.)
3. **Dump the FULL flash** (`0x0–0x3BFFF`). This finally recovers the missing **boot block
   `0x0–0x17FF` + vectors** that the `.rwd` lacks — required for a complete, writable image.
4. **Verify** the dump decodes/round-trips and matches the `.rwd`-derived app region (sanity).
5. **Modify the cal in the complete image:** raise the five ±3840 sites
   (`0x27072/74`, `0x27044/46`, `0x2704C/4E`, `0x2706C/6E`) and the `0x28600` speed table as
   desired — **in BOTH cal banks** (`+0x2E00`) — then **recompute the cal CRC** (the dual-bank
   integrity check; locate it before relying on the write).
6. **Write back** via boot mode (erase + program the whole flash) with a programmer / an
   extended boot-mode tool (renesas-bootmode is read-only today).
7. **Re-verify** by dumping and comparing to the intended image before trusting it on a bench
   rig or vehicle.

🛑 This modifies a steering ECU's torque limits. It is safety-critical: validate on a bench
rig, in stages, with the full gate/telemetry discipline, before any vehicle use. The 240 KB
control firmware is fully mapped (above) to support that — but the actuation substrate (base
power-steering assist + FOC/motor driver, `0x3FFED94 →` motor) is not yet reversed.

## 10. What's mapped vs missing

**Mapped:** image decode, chip/memory map, RAM map, serial LKAS protocol (both directions),
full LKAS torque chain + every clamp/gain/map with addresses, dual cal bank, K-line
diagnostic protocol + telemetry + persistence, reflash-route determination.

**Missing (needs more work or a chip dump):** base power-steering assist + FOC/motor driver;
the bootloader reflash SecurityAccess + flash-write sequence (boot block, not in `.rwd`);
labels for the ~75 telemetry channels (empirical); lockstep/EME/governor/DTC specifics.

See the per-topic notes: `README-T2F-L310-decode`, `MAP-…`, `SERIAL-SUBSYSTEM-…`,
`PROTOCOL-DECODED-…`, `CALIBRATION-…`, `TORQUE-CHAIN-…`, `DIAGNOSTIC-CAPABILITIES-…`,
`GAP-2020-vs-2017`.
