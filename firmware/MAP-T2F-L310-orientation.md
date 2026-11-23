# `39990-T2F-L310` image — byte-level orientation map (pre-Ghidra)

**Date:** 2026-11-23. EVIDENCE (pure byte statistics; no disassembly).
Reproduce: `python -I orient.py 39990-T2F-L310_plain_image.bin` (script in scratchpad;
copy into this dir if kept). Feeds the Ghidra session — these are seeds, not conclusions.

## Code vs data by block

| region | size | 80_07/KB | entropy | class |
|---|---|---|---|---|
| `0x01800–0x07C80` | 25 KB | 0.16 | 6.76 | **CAL/ID** (part IDs + lookup tables) |
| `0x07F80–0x09300` | 5 KB | 0.00 | 6.05 | data |
| **`0x09F80–0x21F80`** | **96 KB** | **6.52** | 7.03 | **CODE (main application)** |
| `0x22580–0x23080` | 2.8 KB | 4.00 | 6.27 | CODE |
| `0x23180–0x25900` | 10 KB | 2.53 | 6.73 | CODE (sparse) |
| `0x26180–0x2A880` | ~18 KB | 0.00 | 4.5–4.8 | data/tables |
| **`0x2B880–0x2EF00`** | **14 KB** | **6.17** | 6.81 | **CODE (second block)** |
| `0x2F080–0x30780` | 6 KB | 0.00 | 7.29 | data (packed) |
| `0x30800–0x33580` | 11 KB | 0.00 | 6.77 | data |
| `0x33600–0x38000` | ~18 KB | ~0 | 4.7–6.3 | data/tables |

**Two code islands: `0x09F80` (main, 96 KB) and `0x2B880` (14 KB).** Everything else
is calibration/data. This is where Ghidra analysis should concentrate.

## Pointer tables (runs of ≥4 consecutive valid LE32)

- **RAM globals cluster `0x03FF9500–0x03FFAE00`** — confirmed by large RAM-pointer
  tables at `0x002B0C` (331 entries), `0x007904` (128), `0x0025F0` (64). This pins the
  RAM working-set layout and re-confirms **RAM base `0x03FF8000`** (device file).
- **Code pointer / jump tables** (point into `0xC000–0x30000`): `0x007B08` (14),
  `0x007C14` (7), `0x002A90` (6), `0x002AD0` (5), `0x007C58` (5). ⇒ candidate switch
  dispatch / function-pointer tables — **high-value Ghidra seeds** for finding handlers.
- `0x028D00` (128× `0x10001`) and `0x0038AC` (`0x1000,0x2000,0x4000…`) are constant/
  bitmask data misread as pointers — ignore.

## Few embedded strings

Only `39990-T2F-L310` (`0x1810`) and `399804G2SC1` (`0x1DB0`). The `0x1800–0x07C80`
"strings" are monotonic lookup-table bytes in printable range, not text. Tightly-coded
EPS with no debug strings — expected.

## For the Ghidra session

1. Language **V850** (E/PG2 ≈ base V850E; confirm variant). Flat, base `0x0`, size
   `0x3C000`. RAM at `0x03FF8000`.
2. Analyze the whole `.bin` first (kit tool policy), then decompile-first.
3. No vector table (boot block absent) ⇒ seed entry points from the **code pointer
   tables above** and the call graph, not from `0x0`.
4. Disassembly MUST go through GhidraMCP — not r2/objdump (kit policy).

## Serial subsystem

The UART/LKAS serial handler is located — see `SERIAL-SUBSYSTEM-T2F-L310.md`. UART driver
(all 3 UARTA channels) at `0x01FE96–0x021426`; CSI/SPI cluster at `0x0218F6–0x021A74`.
Scripts: `serialregs.py` (device-file register map × code search), `uartcluster.py`.
