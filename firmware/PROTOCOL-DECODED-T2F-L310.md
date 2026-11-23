# `39990-T2F-L310` — LKAS serial protocol, decompiled and CONFIRMED

**Date:** 2026-11-23. Ghidra 12.2 headless, `V850:LE:32:default`, flat @`0x0`,
**gp = `0x03FF8000`** (set manually — the reset gp-load is in the missing boot block).
This closes the loop: the 2017 serial model (`model/honda_serial_model.py`) was all
BELIEF about the EPS side; these are the actual EPS bytes. EVIDENCE unless marked.

## Channel: UARTA2 is the camera link (EVIDENCE, two ways)

- `FUN_00020024` sets `U2CTL0=0x1E` ⇒ LSB-first, **even parity, 8-bit, 1 stop = 8E1**;
  `U2CTL1=0x14`, `U2CTL2=0xCD` (baud divisor 205), `U2OPT0=0x14`.
- `FUN_0001ff28` is U2's TX sender with a hard `len < 6` cap → the **5-byte** EPS→camera
  frame. (U0/U1 differ: U1 inits 7-bit/no-parity — not the camera.)

## RX path (camera → EPS, 4-byte frame)

`U2RX ISR FUN_0001fec8` → dispatch `FUN_00023610` (byte assembler) → `FUN_00023200`
(complete-frame processor).

**`FUN_00023610(byte)` — frame sync + assembly** (RAM: idx `0x03FFEC14`, buf `0x03FFED8C`):
```c
if ((b & 0x80) == 0) { idx = 0; FUN_0002338c(); }   // bit7=0 => byte0 = FRAME START
else                 { if (idx<0xff) idx++; }        // bit7=1 => continuation byte
if (idx < 4) { buf[idx] = b; if (idx==3) FUN_00023200(); }   // 4-byte frame, then process
else overflow_ctr++;
```
The `(b & 0x80)==0` start test **is** the model's `is_frame_start` invariant (byte0 bit7=0;
bytes 1-3 bit7=1), now confirmed from the EPS side.

**`FUN_00023200` — field extraction** (buf b0=`ED8C` b1=`ED8D` b2=`ED8E` b3=`ED8F`):
- `b1 & 0x40`, `b1 & 0x20` (LKAS-on, the `0xA0` marker bit), `b0 & 0x40` → status flags.
- `b2 & 0x20` → LKAS-active mirror; `(b2 & 0x18)>>3` → 2-bit field (LDW).
- steer assembled with `<< 5` then a **symmetric ± clamp** (`if (x < lim) … else if (x < ~lim+1)`),
  result → `0x03FFED90` / `0x03FFEC12`. Matches `wire_fields_to_value` + the ±steer limit.
- `FUN_0001ecc8(...)` feeds the steer scale — a lookup; semantics TBD.

## TX path (EPS → camera, 5-byte frame) — the checksum, byte-exact

**`FUN_0002338c`** builds 5 bytes on the stack and sends them:
```c
bStack_15 = MASK[0x27004] | ((v0 & 0x7800) >> 11);   // framing high-bits OR data
bStack_14 = ((v0 & 0x7c0) >> 6) | MASK[0x27005];
bStack_13 = MASK[0x27006] | ((v1 & 0xe000) >> 10);
bStack_12 = MASK[0x27007] | ((v1 & 0x1fc0) >> 6);
bStack_11 = ((~(b0+b1+b2+b3) + 1) & 0x7f) | bStack_11;   // bStack_11 preloaded = 0x80
FUN_0001ed74(0x3ffec00, &bStack_15, 5);   // copy to TX buffer
FUN_0001edac(0x3ffec00, 5);               // send 5 bytes (-> U2 TX, FUN_0001ff28)
```

**Checksum, verified by hand:** `~sum + 1` = `256 − sum`; `& 0x7f` = `% 128`; `| 0x80`
forces `[0x80,0xFF]`. ⇒ `chksm = (256 − sum) % 128 + 128`. **Byte-exact match** to
`honda_serial_model.chksm` — previously BELIEF, now EVIDENCE from EPS firmware.
Checksum is over the 4 data bytes, stored in byte 5. Fixed framing masks live at
`0x27004–0x27007`.

## RAM map discovered (gp-relative, gp=0x03FF8000)

| addr | role |
|---|---|
| `0x03FFEC14` | RX byte index |
| `0x03FFED8C..8F` | 4-byte RX frame buffer (b0..b3) |
| `0x03FFEC00..04` | 5-byte TX frame buffer |
| `0x03FFED90` / `0x03FFEC12` | decoded steer command |
| `0x03FFEC0F` / `0x03FFEC10` | RX overflow / TX error counters |
| `0x03FFEC0A/0C/0E`, `EC15`, `EC0D`, `EC08` | extracted frame flags |

Constant masks: `0x27004–0x27007` (TX framing bits).

## Open (needs more decompiler recovery)

- Several `if(){}` bodies rendered empty (decompiler pruned flag-set bodies with gp set
  but no re-analysis). The load-bearing arithmetic (checksum, masks, shifts) IS present
  and matches; the flag-handling branches are not yet fully recovered. BELIEF: cosmetic,
  not logic — re-run with analysis after applying gp, or inspect in the GUI.
- `FUN_0001ecc8` (steer scale/lookup), and the consumers of the decoded steer at
  `0x03FFED90` — the path toward the motor. That's the next trace (the 2017 analogue of
  the 2020 assist chain).

## Repro

`ghidra/run_headless.sh` (import+analyze) → `ghidra/run_dump.sh` (DumpSerial) →
`ghidra/run_funcs.sh 0x…` (DumpFuncs) → `SetGPDecomp.java 0x3ff8000 0x…` (gp-correct
decompile). Project at `ghidra/project/` (openable in GUI/MCP).
