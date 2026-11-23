# Reference — firmware-dump tooling and the 2017 EPS chip

**Date:** 2026-11-21. Status of each line marked EVIDENCE / BELIEF.

## ⭐ 2026-11-23 — PLAIN IMAGE OBTAINED WITHOUT A CHIP DUMP

The operator supplied the dealer container `39990-T2F-L310.rwd` (9th-gen Accord EPS,
same V850 family). It **decoded cleanly** with the kit's own x31 codec — cipher
`((i−0x9e)^0x10)+0xbf`, key `BF109E`. Result: `analysis-2017accord/firmware/`
`39990-T2F-L310_plain_image.bin` (sha256 `31264ec4…`, 240 KB map base `0x0`, 85.8 %
programmed, verified V850 code + part IDs). See `README-T2F-L310-decode.md`.

**This makes the physical dump OPTIONAL.** The `.rwd` omits only the boot block
(`0x0–0x17FF`: reset/interrupt vectors) and some erased regions — a dump would add
only those. The open items below (renesas-bootmode PG2 path, pin numbers, hookup)
are **no longer on the critical path**; pursue them only if the vector table is
specifically needed. EVIDENCE.

## The tool that produced the 2020's `code.bin`

**`gregjhogan/renesas-bootmode`** (MIT, branch `master`) is a **read-only** serial
boot-mode dumper for Renesas MCUs. Its `v850e2m.py` reads:

- code `0x00000000`–`0x000FFFFF` (1 MB) → `code.bin`
- data `0x02000000`–`0x02007FFF` (32 KB) → `data.bin`

**EVIDENCE of the link to this kit:** those address ranges and the filename `code.bin`
are *identical* to the 2020 kit's memory map and its stock import file
(`FIRMWARE-DECOMPILE-GUIDE.md`: code flash `0x0–0xFFFFF`, data `0x02000000–0x02008000`,
import target `code.bin`). **Conclusion (strong BELIEF):** the 2020 Accord
(`39990-TVA-A160`, µPD70F3508, V850E2/Px4) was dumped with `renesas-bootmode`'s
`v850e2m.py`.

Protocol in `v850e2m.py` (EVIDENCE, from the code): single-wire echo; command header
`0x01` / data header `0x11`; footer `0x03`; checksum `= -sum`; pulse (two `0x00`),
reset `0x00`, oscillator set `0x90`, baud set `0x9A` (115200, but left commented —
stays at 9600), memory read `0x50`. Silicon-signature / checksum verbs are TODO stubs.
Default 9600 baud, oscillator 16 MHz. README V850E2 wiring labels: **TX/RX, FLMD0,
RESET, RTS** (RTS→inverter→RESET).

The SH-2A path (`sh-2a.py`, aliased by `sh72a0.py`/`sh72a2.py` symlinks) is the
**Civic/CR-V** path — that's what the thedordo "Honda Steering Firmware Dump" PDF walks
(chip R5F72A0 / SH72A0, 64-pin). Keycode check sends 16 zero bytes; passes only if no
keycode was set (BELIEF, from a code comment).

## The chip mismatch that matters

| | 2020 Accord (dumped OK) | **2017 Accord (this target)** | Civic/CR-V (the PDF) |
|---|---|---|---|
| Part | µPD70F3508 | **D70F3413** | R5F72A0 |
| Core | V850E2/Px4 | **V850E/CG4 "CarGate"** | SH-2A |
| renesas-bootmode path | `v850e2m.py` ✓ | **needs verification** | `sh-2a.py` |
| Package | (100-LQFP) | 100-LQFP | 64-LQFP |

**BELIEF:** V850E/CG4 (CarGate, an E1-class V850E core) is an *older generation* than the
2020's V850E2. So `v850e2m.py`'s V850E2 boot protocol may NOT match the CarGate boot ROM,
and the `0x0–0xFFFFF` / `0x02000000` address map is for the 2020's 1 MB part, **not** the
smaller CarGate. Both must be checked against the V850E/CG4 User's Manual (`U17411EE1V0UM00`)
before the tool would work on the 2017 unit.

## AUTHORITATIVE for the 3413 — from Renesas device file DF3413.800

Source: `DF703414_v1.00/DF3413.800` (Renesas/NEC device file, the exact binary a
flash programmer/compiler uses) + its `df703414_v100_e.pdf`. EVIDENCE, read 2026-11-21.

- **Part confirmed: µPD70F3413, device-spec name `f3413`, family V850E/PG2.**
  (The PDF: "DF703414 contains device files ... V850E/PG2-F496-C2, F240, M192, M128.")
  ⇒ **V850E/PG2 is a THIRD sub-family** — not the 3433's CG4, not the 2020's V850E2.
- **Code flash: `0x00000000` – `0x0003BFFF` = 240 KB.** This is the `F240` part.
  Cross-check: `DF3414.800` (µPD70F3414) flash end = `0x0007BFFF` = **496 KB = `F496`**.
  So 3413 = 240 KB, 3414 = 496 KB — consistent, two independent confirmations.
- Extra block `0x0003C000` – `0x0003FFFF` = 16 KB (right after flash; likely data/boot
  block — confirm before assuming it's code).
- **Internal RAM: ~`0x03FF8000` – `0x03FFFFFF` ≈ 32 KB** (regions 0x3FF8000–0x3FFAFFF,
  0x3FFB000–0x3FFEFFF, 0x3FFF000–0x3FFFFFF). **RAM base `0x03FF8000`**, NOT the 2020's
  `0xFEDF8000` — different generation.

**Implications:**
- A 3413 code image is **240 KB (`0x0`–`0x3BFFF`)**, not the 2020's 1 MB. renesas-bootmode's
  `v850e2m.py` reads `0x0`–`0xFFFFF`; for the 3413 the code end-address is `0x0003BFFF`.
- For Ghidra later: load `code.bin` flat at `0x0`, 240 KB; RAM at `0x03FF8000`. Different
  base from the 2020 kit's model — do not carry `gp`/`tp`/RAM constants over.
- **V850E/PG2 ≠ V850E2**, so renesas-bootmode (SH-2A + V850E2 only) has **no PG2 path**;
  the boot-ROM protocol must be checked/adapted regardless of the corrected addresses.

## What the 3433 datasheet gives (a DIFFERENT sibling — CG4, not the 3413's PG2)

From the µPD70F3433(A) datasheet the operator supplied (same V850E/CG4 CarGate family;
the 3413 is a sibling, pinout/sizes NOT confirmed to match):

- **Flash: 384 kB, RAM: 32 kB** (3433). → code flash ≈ `0x00000000`–`0x0005FFFF` if the
  3413 is also 384 kB. **The 3413's actual size is unknown** — the lower part number may
  carry less flash. ⇒ the `v850e2m.py` code end-address would change from `0x000FFFFF`.
- **5 V part** (VDD5 = 4.3–5.5 V). The SH-2A PDF's 3.3 V does not apply; match Vcc at 5 V.
- Boot/flash control pins the datasheet names (3433; **unconfirmed for 3413**):
  **FLMD0 = the MODE pin** ("FLMD0 is shared function of the MODE pin"); **FLMD1 = PDL5**;
  plus **RESET**, **X1/X2** (oscillator), and VDD5/VSS5 power/ground groups. UARTA0 =
  **P30 (RXDA0) / P31 (TXDA0)**, bottom edge.
- Flash programming: via flashPRO4 **or** self-programming (datasheet §2). Serial write
  characteristics in §3.7 reference FLMD0 timing.

## Open items before a 2017 dump is possible

1. ~~Confirm the 3413's flash size~~ **DONE: 240 KB, `0x0`–`0x3BFFF`** (DF3413.800). The
   dumper's code end-address is `0x0003BFFF`, not `0x000FFFFF`.
2. **Confirm renesas-bootmode's V850 path speaks the V850E/PG2 boot protocol**, or adapt it.
   The tool has SH-2A + V850E2 paths only; the 3413 is **V850E/PG2**, a third generation.
3. **Confirm the 3413 pin numbers** for FLMD0/MODE, RESET, the boot UART, and power — the
   3433 numbers are a starting reference only.
4. Physical hookup / mode-entry procedure: community-sourced (openpilot / whoever dumped
   the 2020), per renesas-bootmode's own V850 wiring diagram.
