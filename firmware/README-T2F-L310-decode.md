# 2017 Accord EPS firmware — `39990-T2F-L310` decoded from dealer `.rwd`

**Date:** 2026-11-23. Every line marked EVIDENCE / BELIEF.

This is the path that **sidesteps the physical chip dump entirely.** Instead of
reading flash off the µPD70F3413 over a boot UART, we decoded Honda's own dealer
reflash container to the plain V850 image.

## Source

- **Container:** `39990-T2F-L310.rwd` (214 232 bytes), supplied by the operator,
  kept on his Desktop — **not** committed here (Honda-copyrighted).
- **Part:** `39990-T2F-...` = **9th-gen (2013–2017) Accord EPS**, V850 family.
  Same family the kit's `encode_eps.py`/`decode_eps.py` already round-trips
  byte-identically (T2F, T3L, TV9). EVIDENCE.
- Container `/` header: `39990-T2F-L300` → `39990-T2F-L310` (an **L300→L310 update**).
- Container `!` header: `001100121020` — the V850 **family marker**, not a secret
  (see `reference-honda-eps-sa-secret-per-mcu-family`). EVIDENCE it's V850.

## The decode (EVIDENCE)

- **Format:** x31. **Cipher key** (`&` header): `BF109E`.
- **Correct cipher:** `plain = ((cipher − 0x9e) ^ 0x10) + 0xbf`  (byte-wise, &0xFF).
- **Reproduce:** `python -I decode_t2f_rwd.py <path-to.rwd>` → writes
  `39990-T2F-L310_plain_image.bin`.

### ⚠ The ambiguity trap — why `matches[0]` is WRONG here

Cracking on "the part-number string appears in the plaintext" is **not sufficient**.
Two distinct 256-byte tables both decode the 14-byte part string to
`39990-T2F-L310` but diverge on the code:

| table | 2nd-commonest plaintext byte | 0xFF population | verdict |
|---|---|---|---|
| `((i−0x9e)+0xbf)^0x10` (cracker `matches[0]`) | `0x1F` | 0.15 % | **decoy — WRONG** |
| `((i−0x9e)^0x10)+0xbf` | `0xFF` | 3.76 % | **CORRECT** |

Separator is the **padding byte**, not the string. Honda pads programmed blocks to
128-byte boundaries with erased-flash `0xFF`; 0.15 % `0xFF` across 210 KB is
physically impossible. The ID block confirms it: under the correct table the part
string is followed by clean `0xFF` padding; under the decoy, by `0x1F` garbage.
**`decode_t2f_rwd.py` hardcodes the correct table and asserts the `0xFF` test.**

## The image (EVIDENCE)

- **File:** `39990-T2F-L310_plain_image.bin`
- **sha256:** `31264ec49e638a41f6d6adaa05b69f79ba9d95a9074965ab1130b1c816a1d372`
- **Size / base:** `0x3C000` (245 760 B), based at **`0x0`** (= the 3413's 240 KB
  code-flash map `0x0–0x3BFFF`, per device file DF3413.800).
- **Programmed:** 210 816 B = **85.8 %** of flash. The rest is `0xFF` (gaps below).
- **Confirmed content:** part IDs `39990-T2F-L310` (@`0x1810`) and `399804G2SC1`
  (@`0x1DB0`); structured calibration data from `0x1820`; **genuine V850 code** —
  densest window `0x013C00` (89 `80 07`/2 KB, recurring `60 3f XX 90` ops).

## ⚠ What a `.rwd` does NOT contain (BELIEF → plan around it)

A dealer container holds only the **reprogrammed** blocks, so these are absent
(all `0xFF` in the image):

- **`0x0 – 0x17FF` (6 KB): the boot block + reset/interrupt vector table.** Honda's
  reflash protects it. ⇒ no reset vector, no ISR vector table. Entry points for
  Ghidra must be found heuristically (call-graph roots), not read from `0x0`.
- `0x38000 – 0x3BFFF` (16 KB) and small inter-block gaps: erased / EEPROM-emulation.

Full gap list: `0x0–0x1800`, `0x7C80–0x7F80`, `0x9300–0x9F80`, `0x21F80–0x22580`,
plus ~15 small `0x80`-sized gaps, and `0x38000–0x3C000`.

## Loading in Ghidra (plan)

- Language **V850** (E/PG2 is base V850E; confirm the exact variant in the manual).
- **Flat, base `0x0`, size `0x3C000`.** Internal RAM at **`0x03FF8000`** (device
  file), NOT the 2020's `0xFEDF8000`. Do **not** carry any 2020 `gp`/`tp`/RAM
  constants over — different generation.
- No vector table ⇒ let auto-analysis find functions, then seed from the call graph.
- Get Ghidra to analyze the whole `.bin` first (per kit tool policy), then work
  decompile-first.

## Cross-checks that all agree (EVIDENCE)

1. Image fits inside the 3413's 240 KB map with room to spare (max addr `0x38000`
   < `0x3BFFF`) — consistent with the physical D70F3413 being the 240 KB part.
2. V850 family marker in the `!` header + `80 07` code density (6.52/KB on the big
   block) = V850 code, consistent with V850E/PG2.
3. Kit already decodes sibling `39990-T2F-A210` / `39990-T3L-A210` with the same
   codec.

## Files here

- `39990-T2F-L310_plain_image.bin` — the decoded image (above).
- `decode_t2f_rwd.py` — reproducible decoder (correct table + padding-byte assert).
- `README-T2F-L310-decode.md` — this file.

> Per kit convention large firmware binaries live in the `accord-firmwares` repo and
> are gitignored in the kit. This 2017 tree is currently untracked; if/when it's
> committed, move the `.bin` to `accord-firmwares` and leave a pointer here.
