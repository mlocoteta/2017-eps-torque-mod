# `39990-T2F-L310` — calibration-table map

**Date:** 2026-11-23. Byte-level structure only (no disassembler). Locates and
characterises the tables; **assigning semantics** (which curve is the assist map, what
each axis is) **needs Ghidra** to follow the code that reads them. EVIDENCE = byte
structure; BELIEF = any guess at meaning.

## ⭐ Dual calibration bank (EVIDENCE — verified byte-identical)

The firmware keeps **two identical copies** of its main cal block, `0x2E00` apart:

- **Bank A: `0x02F100 – 0x031F4E`** (~11.8 KB)
- **Bank B: `0x031F00 – 0x034D4E`** — byte-identical to A (sha256 `d64fc6c9…` both).

All 11 detected curve-pairs match at +`0x2E00`. This is standard safety-ECU cal
redundancy (primary + backup, almost certainly CRC-checked against each other).

> 🛑 **Consequence for any future edit:** a calibration change must be written to
> **both banks** and the governing CRC recomputed, or the ECU faults on bank mismatch.
> This is the 2017 analogue of the 2020 kit's `.rwd` CRC discipline.

## Large math / interpolation tables (EVIDENCE)

- `0x0038EC`: **4097-pt** linear ramp `0 → 16384` (`0x4000`). 2¹²-indexed — likely an
  interpolation/linearisation LUT, not a tuning map.
- `0x0058EE`: **4096-pt** ramp `0 → 2048`, unit step. Same class.

## Lookup curves (EVIDENCE — candidate tuning tables, semantics TBD)

Inside the dual-bank region (per bank), e.g. (Bank-A addresses):

| addr | pts | shape | range |
|---|---|---|---|
| `0x02F100` | 512 | UP | 0 → 20494 |
| `0x02F7A6` | 493 | UP | 5 → 32294 |
| `0x02FE02` | 511 | UP | 31 → 9857 |
| `0x031502` | 511 | UP | 0 → 27591 |
| `0x031A00` | 253 | UP | 0 → 18021 |
| `0x02F582` | 274 | DN | 22215 → 0 |
| `0x030282` | 216 | DN | 13924 → 2978 |

**256-entry byte-indexed tables** (likely sensor-byte → value maps), in `0x027xxx`:
`0x027200` (0→3341), `0x027400`/`0x027A00` (0→7453), `0x028000` (−258 → −32383 DN),
`0x028802` (18→4352). These 2⁸-entry tables are the most "map-like" — a single 8-bit
input (speed? torque? temperature?) indexing a shaped output.

**Standalone DN curves** at `0x030800` / `0x033600` (dup): 897-pt `25000 → 0` — `25000`
reads like a scaled ceiling (250.00 units?). `0x034CFE`: 1145-pt `22271 → 0`.

Values cluster near int16 full-scale (`32767`, `32384`, `32294`) ⇒ many are Q15 / raw
fixed-point. Scales unknown until the readers are decompiled.

## The ID/front cal block `0x1800–0x07C80`

Holds the part IDs (`39990-T2F-L310` @`0x1810`, `399804G2SC1` @`0x1DB0`), small structured
tables (`0x1820`+), and the two big interp LUTs above. Entropy ~6.8 — dense packed cal.

## For Ghidra

Label the two banks; find the CRC routine that compares them (seed from the bank
boundaries). Then follow reads of the 256-entry `0x027xxx` tables and the 511-pt curves
to name the assist/torque maps — the 2017 analogue of the 2020 assist-map / boost-index
work. Scripts: `calscan.py`, `dualbank.py`.
