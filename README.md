# 2017 Accord EPS Torque Mod

Reverse-engineering of the **2017 Honda Accord (9th-gen) electric power-steering
firmware**, `39990-T2F-L310` (Renesas **µPD70F3413, V850E/PG2**), as the sibling effort to
the 2020 Accord (`39990-TVA-A160`, V850E2) torque-mod kit in this repo.

**The headline: the 2017 is a different platform from the 2020, and this maps the
difference end to end — including why LKAS torque is capped at ±240, and how/whether it can
be flashed.** Everything below was obtained without a chip dump — by decoding the dealer
`.rwd` and analysing the plain image in Ghidra (headless, V850, gp=`0x03FF8000`).

Firmware binaries are **not** committed here (Honda-copyrighted; kept in the sibling
`accord-firmwares` tree per repo convention). What's here is the analysis, the reproducible
scripts, and the findings.

## How the 2017 differs from the 2020 (the important part)

| | 2020 Accord (TVA) | **2017 Accord (T2F)** |
|---|---|---|
| MCU | µPD70F3508, V850E2/Px4 | **µPD70F3413, V850E/PG2** (240 KB flash) |
| LKAS command transport | **CAN** `STEERING_CONTROL` (0xE4/228) | **Serial UART** (camera ↔ EPS, 9600 **8E1**, UARTA2) |
| Diagnostics / reflash transport | CAN **UDS** (`0x10/0x27/0x34…`) | **K-line**, Honda-proprietary (`0xC0–0xC7`) |
| SecurityAccess | `(seed+k0)^((seed*k1)%k2)`, consts @`0x92C0` | **bootloader-resident** (not in the `.rwd` image) |
| Flasher | kit's `eps-update-tva.py` (CAN) | needs a **K-line** tool; CAN flasher does **not** apply |
| Torque controller | LKAS rate PID | **same PID structure**, different addresses |

Both are Honda V850 EPS with the *same torque units* — the Honda DBC `STEER_TORQUE
[-3840|3840]` range equals this firmware's internal ±3840 clamp (the serial path's `×16`
maps the 9-bit wire value into that space).

## Current findings

- **Decoded the dealer `.rwd`** (x31, cipher `((i-0x9e)^0x10)+0xbf`) → plain 240 KB V850
  image; firmware part string confirms the decode. See `firmware/README-T2F-L310-decode.md`.
- **Serial LKAS protocol confirmed byte-exact from the EPS side** (framing, 4-byte RX /
  5-byte TX, the `(256−sum)%128+128` checksum, 9-bit steer decode) — previously only a
  model. See `firmware/SERIAL-SUBSYSTEM` + `PROTOCOL-DECODED`.
- **Full LKAS torque chain traced**: serial decode → demand clamp (±240) → dynamic clamp →
  **PID** (assist map `0x28800`, Kp `0x28B00`, Kd `0x28C00`, per-term clamps) → gains →
  **output clamp** → engage/rate-limit/taper → motor. See `firmware/TORQUE-CHAIN`.
- **Why ±240:** a hard cal clamp `±3840 = ±240×16`, enforced in **three** places
  (`0x27072/74` demand, `0x27044/46` P-term, `0x2704C/4E` output). It's the EPS, not just
  the camera. See `firmware/PROTOCOL-DECODED` / `TORQUE-CHAIN`.
- **2020→2017 torque-mod lever map** (clamps, Ki, gains, maps) in `firmware/GAP-2020-vs-2017.md`.
- **Flashing:** diagnostics run over **K-line** (`0xCx` commands, service `0xC2` =
  SecurityAccess for *diagnostics/adjustment*). **Main firmware reflash + its security are
  in the boot sector `0x0–0x17FF`**, which the `.rwd` does not contain — so reversing the
  reflash needs a chip dump of that 6 KB boot block. See `firmware/GAP-2020-vs-2017.md`.
- **Calibration:** dual redundant cal bank (`0x02F100`↔`0x031F00`, byte-identical) — any
  cal edit must touch both + CRC. See `firmware/CALIBRATION`.

## Layout

```
firmware/
  README-T2F-L310-decode.md    decode record (cipher, blocks, caveats)
  MAP-T2F-L310-orientation.md  code/data map, RAM layout, pointer tables
  SERIAL-SUBSYSTEM-T2F-L310.md UART driver + register map
  PROTOCOL-DECODED-T2F-L310.md serial LKAS protocol, decompiled + confirmed
  CALIBRATION-T2F-L310.md      cal tables + dual-bank redundancy
  TORQUE-CHAIN-T2F-L310.md     full serial→motor torque chain + 2020 lever map
  GAP-2020-vs-2017.md          what the 2020 mapped vs 2017; flashing analysis
  decode_t2f_rwd.py            reproducible .rwd → image decoder
  orient.py / serialregs.py / uartcluster.py / calscan.py / dualbank.py   byte-level tools
  ghidra/                      headless Ghidra runners + Java analysis scripts
notes/                         dump-tooling + chip reference
model/                         byte-exact serial protocol model (from the fork board)
```

## Reproduce

Decode: `python -I firmware/decode_t2f_rwd.py <39990-T2F-L310.rwd>`.
Ghidra (needs JDK 25): `firmware/ghidra/run_headless.sh` (import+analyse), then the
`run_*.sh` / `*.java` scripts (all decompiles use gp=`0x03FF8000`).

> Status: analysis/feasibility. No modified build has been produced or flashed. Modifying a
> steering ECU's torque limits is safety-critical and out of scope for this mapping work.
