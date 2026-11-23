# `39990-T2F-L310` — serial subsystem located (the LKAS link bytes)

**Date:** 2026-11-23. Method: device-file register map (DF3413.800) × firmware
displacement search. **No disassembler used** — this is byte evidence that *locates*
the handler; reading its logic needs Ghidra.

## How it was found

Direct constant search for the protocol (checksum `0x7F|0x80`, frame markers `0xA0`)
**failed** — those bytes collide with V850's ubiquitous `80 07`/`c0 07` opcode bytes.
Instead: the LKAS link is a **UART** (9600 8E1), so the handler must touch UARTA
registers. Extracted their addresses from `DF3413.800`, then searched the code for the
access displacements. V850 reaches the peripheral area (`0xFFFFF000+`) via
`ld.b/st.b 0xFAxx[r0]`, so each register's low-16 displacement is a literal halfword
in the instruction stream.

## Serial register map (EVIDENCE — from DF3413.800, peripheral base `0xFFFFF000`)

UARTA (asynchronous — the LKAS family), 16-byte stride per channel:

| reg | U0 (A0) | U1 (A1) | U2 (A2) |
|---|---|---|---|
| CTLn0 (enable/mode) | `FFFFFA00` | `FFFFFA10` | `FFFFFA20` |
| CTLn1 | `FFFFFA01` | `FFFFFA11` | `FFFFFA21` |
| CTLn2 (clock sel) | `FFFFFA02` | `FFFFFA12` | `FFFFFA22` |
| OPTn0 (parity/stop) | `FFFFFA03` | `FFFFFA13` | `FFFFFA23` |
| STRn (status) | `FFFFFA04` | `FFFFFA14` | `FFFFFA24` |
| **RXn (receive)** | `FFFFFA06` | `FFFFFA16` | `FFFFFA26` |
| **TXn (transmit)** | `FFFFFA08` | `FFFFFA18` | `FFFFFA28` |

CSI (synchronous/SPI — `S0/S1`): a separate block near `0xFFFFF900` (device-file parse
of the CTL0 offset was unreliable; verify in Ghidra). **Not** the async LKAS link.

## The UART driver — located (EVIDENCE)

**All three UARTA channels are initialised and serviced in one contiguous block,
`0x01FE96 – 0x021426`.** Each channel shows the same init+service shape — STR polled,
TX written, then CTL0/CTL1/CTL2/OPT0 set up:

| channel | region | STR poll | TX | init (CTL0/1/2/OPT0) |
|---|---|---|---|---|
| **UARTA2** | `0x01FE96–0x02004x` | `0x01FE96` | `0x01FF08/54/84` | `0x01FF96–0x020046` |
| **UARTA1** | `0x021226–0x02132A` | `0x021226` | `0x021280` | `0x02128A–0x02132A` |
| **UARTA0** | `0x02133A–0x021426` | `0x02133A` | `0x02134C` | `0x0213AA–0x021426` |

Other scattered UARTA touches: `U0CTL0` @`0x0100C7`, `0x014456`, `0x02156D`;
`U0CTL2` loop @`0x01EAAF–0x01EAE7`; `U2CTL0` @`0x01BABA`.

Strong **CSI (S1)** cluster at `0x0218F6–0x021A74` (12× TX, 6× RX disp) — the
synchronous bus, likely torque-sensor/companion-IC SPI, **not** the camera link.

## What's pinned vs what still needs Ghidra

**EVIDENCE (byte-level):**
- The UARTA register addresses (reusable SVD fragment, above).
- The UART TX + init driver for all three channels: `0x01FE96–0x021426`.

**BELIEF / open (needs Ghidra — RX reads are invisible to displacement search because
the RX ISR loads the base into a register):**
1. **Which channel is the camera link.** Three UARTA channels are active; the LKAS one
   is 9600 8E1. Discriminator = the baud divisor + OPT0 (even parity) immediates in
   each init block — read them in Ghidra, or decode the immediates by hand.
2. **The RX decode** — checksum validation `(256−sum)%128+128`, the 9-bit steer-field
   extract, counter/LKAS-on/LDW bit handling. Lives in the RX interrupt handler,
   reached from the channel's RX vector. Seed Ghidra from the RX register `0xFA06/16/26`
   xrefs and the driver region above.
3. **The TX frame build** — the 5-byte EPS→camera frame (motor torque, sign bits) and
   the shared checksum routine, called from the LKAS channel's TX at one of
   `0x01FF08`/`0x021280`/`0x02134C`.

## For the Ghidra session

Load the driver region first; label the UARTA registers from the map above; follow the
RX-register xrefs into the interrupt handler to reach the checksum/steer-decode — that
is the 2017 analogue of the 2020 `eps_lkas_chain_model` intake path.
