# `39990-T2F-L310` — K-line diagnostic capabilities (no reflash)

**Date:** 2026-11-23. What the EPS exposes over its **K-line** serial diagnostic port
(UART U1, Honda proprietary protocol) — usable on the bench **without** touching flash or
the bootloader security. EVIDENCE from decompilation unless marked.

Request framing: length-prefixed; dispatcher `FUN_0001da3c` branches on command byte.
Response checksum = `~sum+1` (`FUN_0001ecec`).

## Command map (service byte → handler)

| cmd | handler | what it does |
|---|---|---|
| `0x7D` | `FUN_0001c488` | (readout) |
| `0xC0` | `FUN_0001d928` | **read live data by index** (telemetry) — see below |
| `0xC1` | `FUN_0001d8d0` | readout |
| `0xC2` | `FUN_0001d71c` | **sub-dispatcher**: SecurityAccess toggle, memory read/program, actuator test |
| `0xC3` | `FUN_0001d2b4` | sub-commands `0x04 F0/F1` |
| `0xC4` | `FUN_0001d258` | read-by-id (`05 71`, `07 72`, `05 73`) |
| `0xC5` | `FUN_0001cb28` | **read ECU IDs** (part `399804G2SC1` @`0x1DB0`, serials @`0x3FFDA58/68`) |
| `0xC7` | `FUN_0001ca48` | gated sub-dispatcher (post-"unlock") — more readouts |
| `0xFE` | `FUN_0001da08` | (reset/keepalive) |

`0xC0`/`0xC7` are gated by an "unlocked" flag (`0x3FFD438 & 8`) set by `0xC2 06 C7 01` —
a **diagnostic** gate, not the reflash crypto (that's bootloader-resident; see
`GAP-2020-vs-2017.md`).

## 1. Live-data telemetry — `0xC0` (no security)  ⭐ most useful on the bench

`FUN_0001d928`: request **`C0 05 <index> <count>`** (count 1–16) → returns `count` bytes
read through a **pointer table at flash `0x8EFC`** (≈151 entries = ~75 **16-bit** channels,
each value = two consecutive entries, high byte first). The channels point into the EPS
measurement block **`0x3FF9600–0x3FF9AD0`** (+ a few at `0x3FFACxx`).

- To read 16-bit channel *k*: `C0 05 <2k> 02`.
- Channel **meanings are not labelled in firmware** — identify empirically on the bench
  (read a channel while applying torque/steer/ignition and watch which moves). The table
  order is fixed, so a one-time calibration map is reusable.
- This is the clean path to instrument the bench EPS (torque sensor, motor current, angle,
  temperature, fault state, etc.) over 3 wires, no CAN, no security.

## 2. Read ECU IDs — `0xC5` (no security)

Returns the software ID string and stored serials — useful to confirm the part/rev of a
bench unit before anything else.

## 3. Actuator self-test — `0xC2 06 A3` (enter) / `0xC2 … A4` (set params)

`0xA3` (`FUN_000170fc`) enters test mode (`cRam03ffd7a8=1`) after interlock checks
(vehicle stopped, no faults). `0xA4` (`FUN_00016f80`) loads test **parameters**
(`0x3FFDCBA…CCA`). The sequencer `FUN_000176a0` then steps a **canned test pattern**; the
test flag feeds the control state machine (`FUN_0000FAC0`). ⚠ This runs a **predefined
self-test**, parameterised — **not** an arbitrary "command N Nm" interface. BELIEF: it can
move the motor in the factory test pattern, but is not a free torque-command channel.

## 4. Bounded adjustment write — `0xC2 06 03/08` (gated)

`FUN_0001d650`/`FUN_0001d6a8` → `FUN_00010614`/`FUN_0001a160`: a **bounds-checked**
RAM/parameter write (addr bounds `0x4000`/`0x8000`; value bounds `DAT_0x1F6C…203E`), gated
by a mode flag, dispatched via a mailbox (`0x3FFCD54`) to another subsystem. BELIEF: a
service adjustment (e.g. torque-sensor zero / variant setting), **not** general cal
tuning. Exact target not yet resolved — a candidate no-reflash tune lever **if** it reaches
a torque-relevant value; needs the mailbox-consumer trace to confirm.

## What this does NOT give (needs the bootloader / a chip dump)

Main-flash reprogramming and its SecurityAccess — bootloader-resident, not in this image.
So the torque-ceiling cal edits (`0x27044/46`, `0x2704C/4E`, etc.) still require a **flash**
(bootloader path), not any of the above K-line commands. See `GAP-2020-vs-2017.md`.

## Next traces (all possible from THIS image)

1. **Resolve the `0xC2 03/08` adjustment-write target** (mailbox `0x3FFCD54` consumer) —
   is any torque-relevant value live-writable without reflash?
2. **Label the top `0xC0` telemetry channels** by cross-referencing which control-loop
   variable each `0x3FF96xx` mirror is written from (motor current, torque, angle).
3. **Base power-steering assist + motor driver** (`0x3FFEC2E` → motor) — the normal EPS
   function, still unmapped.
