"""
Byte-exact Python mirror of the 2016/2017 Accord LKAS<->EPS 9600 8E1 serial link,
as implemented by the operator's LKAS_EPS_V3 firmware (STM32F103, "V2/V3 board").

STATUS OF EVERY CLAIM IN THIS FILE
  EVIDENCE  = re-derived line-by-line from LKAS_EPS_V3 C source (cited by file:function).
  BELIEF    = inference about what the *EPS firmware* does. NOTHING here has been
              checked against 2017 EPS firmware bytes, because we do not have an
              image yet. Treat every "the EPS presumably..." as unproven.

This is the 2017 analogue of analysis-2020accord/model/eps_lkas_chain_model.py:
the authoritative mirror that log decoding and any later firmware work are
scored against. Mirrors the C arithmetic exactly -- integer ops, real widths,
explicit uint8_t/int8_t/int16_t truncation. No numpy, no floats in the wire path.

Source of truth:
  LKAS_EPS_V3/src/hondaSerial.cpp   -- framing, encode, decode
  LKAS_EPS_V3/src/checksums.cpp     -- chksm()
  LKAS_EPS_V3/src/canMessages.cpp   -- handleLkasFromCan(), torque_blend()
  LKAS_EPS_V3/include/common.h      -- steerMax et al
"""

# ---------------------------------------------------------------- width helpers
def u8(x):   return x & 0xFF
def u16(x):  return x & 0xFFFF
def i8(x):   return (x & 0xFF) - 256 if (x & 0x80) else (x & 0xFF)
def i16(x):  return (x & 0xFFFF) - 65536 if (x & 0x8000) else (x & 0xFFFF)

# -------------------------------------------------------- common.h #defines
steerMax              = 239
steerThreshold        = 30
steerDeltaUp          = 100
steerDeltaDown        = 100
steerDriverAllowance  = 30
steerDriverMultiplier = 18
steerDriverFactor     = 1


# =============================================================== SECTION 1
# checksums.cpp :: chksm(b0,b1,b2)
# =========================================================================
def chksm(*parts):
    """EVIDENCE - checksums.cpp:chksm. `tot` is uint8_t so the sum wraps mod 256,
    but (256-tot)%128 == (-sum)%128 either way, so the wrap is harmless.

    The `%128 + 128` is NOT cosmetic: it forces the checksum into [0x80,0xFF],
    i.e. top nibble >= 8. That is what makes the checksum byte structurally
    impossible to mistake for a frame-start byte (see is_frame_start)."""
    tot = u8(sum(parts))
    tot = u8(256 - tot)
    tot %= 128
    tot += 128
    return tot


def is_frame_start(b):
    """EVIDENCE - hondaSerial.cpp:deconstructLKAS and :EPStoLKAS both resync on
    `(msg >> 4) < 4`. So the wire framing invariant is:

        byte 0  -> top nibble in {0,1,2,3}
        bytes 1+-> top nibble in {4..15}

    Byte 1 is `steerB0 | 0xA0` (>=0xA0), byte 2 is 0x80/0xC0, byte 3 is the
    checksum (>=0x80). All >= 4 in the top nibble. The invariant holds by
    construction -- it is a real protocol design feature, not an accident."""
    return (b >> 4) < 4


# =============================================================== SECTION 2
# canMessages.cpp :: handleLkasFromCan  -- openpilot int16 -> wire nibbles
# =========================================================================
def op_to_wire_fields(steer_blended):
    """EVIDENCE - canMessages.cpp:handleLkasFromCan.

        steerMSB_blend = blended >> 8          (uint8)
        steerLSB_blend = blended & 0xFF        (uint8)
        steerB1  = ((steerMSB_blend >> 4) & 0x08)   <- sign  = bit15 of blended
                 | ((steerLSB_blend >> 5) & 0x07)   <- magnitude bits [7:5]
        steerB0  =   steerLSB_blend & 0x1F           <- magnitude bits [4:0]

    So the wire field is a 9-BIT TWO'S-COMPLEMENT value:
        bit8 = sign, bits[7:0] = low byte of the int16.
    Representable range -256..+255. Anything outside wraps silently."""
    msb_blend = u8(i16(steer_blended) >> 8)
    lsb_blend = u8(steer_blended)

    steerB1 = ((msb_blend >> 4) & 0b00001000) | ((lsb_blend >> 5) & 0b00000111)
    steerB0 = lsb_blend & 0b00011111
    return steerB1, steerB0


def wire_fields_to_value(steerB1, steerB0):
    """EVIDENCE - canMessages.cpp:handleLkasFromCan, the apply_steer readback.
    This is the decode the EPS must be doing (BELIEF that the EPS matches it,
    but the readback in the operator's own code is the only spec we have)."""
    v = ((steerB1 & 0b00000111) << 5) | steerB0
    if (steerB1 >> 3) == 1:
        v |= 0xFF00
    return i16(v)


# =============================================================== SECTION 3
# hondaSerial.cpp :: serialSteerToEPS  -- THE WIGGLE BIT
# =========================================================================
def encode_lkas_to_eps(counterBit, steerB1, steerB0, prev_lsb,
                       ldw_enable=0, send_frame_delay=0):
    """EVIDENCE - hondaSerial.cpp:serialSteerToEPS(struct Status*).

    The load-bearing line:

        if (steerB1 > 0 || steerB0 > 0) {
            steerB0 = steerB0 & 0b00011110;                 // keep bits [4:1]
            steerB0 = steerB0 | ((steerLSB ^ 1) & 0b1);     // bit0 := toggle
        }

    ==> BIT 0 OF THE MAGNITUDE IS NOT DATA. It is overwritten every frame with
    the inverse of the previous frame's bit0. The C comment says the EPS errors
    out without this "wiggle".

    CONSEQUENCE (EVIDENCE, by construction): the commandable resolution is NOT
    9 bits. It is sign + 7 magnitude bits, and the delivered value alternates
    +/-1 LSB every frame at 100 Hz. Commanded 230 and 231 are the same command.

    Returns (msg[0..3], new_prev_lsb)."""
    if send_frame_delay > 0:
        steerB0 = 0
        steerB1 = 0
    else:
        if steerB1 > 0 or steerB0 > 0:
            steerB0 = steerB0 & 0b00011110
            steerB0 = steerB0 | ((prev_lsb ^ 1) & 0b00000001)

    msg = [0, 0, 0, 0]
    msg[0] = u8((counterBit << 5) | steerB1)
    msg[1] = u8(steerB0 | 0xA0)              # 0xA0: bit5 = LKAS ON
    msg[2] = u8(0x80 | ldw_enable)           # 0x80 = ON, 0xC0 = OFF
    msg[3] = chksm(msg[0], msg[1], msg[2])

    new_prev_lsb = steerB0 & 0b00000001
    return msg, new_prev_lsb


# =============================================================== SECTION 4
# hondaSerial.cpp :: calculateSteerTorque -- EPS -> LKAS driver torque
# =========================================================================
def calculate_steer_torque(eps_b0, eps_b1):
    """EVIDENCE - hondaSerial.cpp:calculateSteerTorque.

        lsb  = (data[0] << 5)                (uint8 -- TRUNCATES to 8 bits)
        lsb |= data[1] & 0x1F
        lsb  = ~lsb                          (uint8)
        msb  = (~(data[0] >> 3)) & 0x01
        steerTorque = msb << 8 | lsb         (int16)

    NOTE the result is ALWAYS in [0, 511] -- msb is one bit, lsb is a uint8.
    It is never negative. Sign lives in bit 8, so "zero driver torque" sits
    near 255/256, not near 0. That matters a lot downstream (SECTION 5)."""
    lsb = u8(eps_b0 << 5)
    lsb |= eps_b1 & 0b00011111
    lsb = u8(~lsb)
    msb = u8(~(eps_b0 >> 3)) & 0b00000001
    return i16((msb << 8) | lsb)


# =============================================================== SECTION 4B
# MOTOR TORQUE -- EPS -> LKAS bytes 2 and 3
# =========================================================================
def calculate_motor_torque(eps_b2, eps_b3):
    """EVIDENCE, derived from 39 037 checksum-valid EPS frames across four
    drives -- NOT from the C, which gets this wrong (see below).

    Layout:
        b2  [1][flag6][ s ][ s ][ s ][f2][0][f0]
        b3  [1][ m6 ][ m5 ][ m4 ][ m3 ][m2][m1][m0]

    b2 bits 5,4,3 are ONE sign bit, replicated -- a sign extension. Measured:
    b2[5:3] is 000 (20 755x) or 111 (18 239x) in 99.89% of frames; the other
    five combinations account for 43 frames total. b2 bit7 and b3 bit7 are
    always set, which is structural: the framing invariant requires every
    non-first byte to have a high top nibble.

    So motor torque is an 8-BIT SIGNED value: sign from b2 bit3, magnitude
    from b3[6:0]. Observed range -127..+126, median 0.

    Validation: correlation with the commanded LKAS steer, 3 ms lag --
        all frames      r = +0.476   (most motor torque is driver assist)
        |cmd| >= 100    r = +0.817
        |cmd| >= 200    r = +0.872   (the lane-departure shake; LKAS dominates)

    WHAT LKAS_EPS_V3 DOES INSTEAD (canMessages.cpp:txMotorTorque):
        motorTorque  = (epsData[2] & 0b00110000) << 4;   // b2[5:4] -> bits 9:8
        motorTorque |= (epsData[2] & 0b00001000) << 4;   // b2[3]   -> bit 7
        motorTorque |= (epsData[3] & 0b01111111);        // b3[6:0] -> bits 6:0
        if (motorTorque & 0x0200) motorTorque = ~(abs(motorTorque)) & 0x01FF;

    It spreads the single sign bit across three MAGNITUDE positions, then
    "corrects" with ~x & 0x1FF, which cannot produce a negative number. Result:
    46.8% of frames are negative, and the fork emits ZERO negative frames --
    its output range is 0..265. r = +0.110 during the shake, i.e. noise.

    It is accidentally RIGHT for positive torque (b2 = 0x80, all sign bits
    clear, so the extra terms contribute 0), which is why it half-works."""
    mag = eps_b3 & 0x7F
    return mag - 128 if ((eps_b2 >> 3) & 1) else mag


def motor_torque_fork(eps_b2, eps_b3):
    """The LKAS_EPS_V3 version, for side-by-side comparison. Do not use."""
    v = ((eps_b2 & 0b00110000) << 4) | ((eps_b2 & 0b00001000) << 4) | (eps_b3 & 0x7F)
    if v & 0x0200:
        v = (~v) & 0x01FF
    return v


# =============================================================== SECTION 5
# canMessages.cpp :: torque_blend
# =========================================================================
def torque_blend(apply_torque, apply_torque_last, driver_torque_raw):
    """EVIDENCE - canMessages.cpp:torque_blend.

        int8_t driver_torque = driverTorque >> 1;

    driverTorque is calculate_steer_torque()'s output, which SECTION 4 proves is
    in [0,511] and centred near 256. So:

        driverTorque = 256 (wheel at rest) -> >>1 = 128 -> int8_t = -128   (!!)

    The int8_t truncation flips sign exactly at the centre of the signal's
    range. See the demo in __main__ for the consequence."""
    at = apply_torque
    atl = apply_torque_last
    driver_torque = i8(driver_torque_raw >> 1)      # <-- the int8_t truncation

    driver_max = steerMax + (steerDriverAllowance + driver_torque * steerDriverFactor) * steerDriverMultiplier
    driver_min = -steerMax + (-steerDriverAllowance + driver_torque * steerDriverFactor) * steerDriverMultiplier
    max_allowed = max(min(steerMax, driver_max), 0)
    min_allowed = min(max(-steerMax, driver_min), 0)

    if atl > 0:
        at = _clip(at, max(atl - steerDeltaDown, -steerDeltaUp), atl + steerDeltaUp)
    else:
        at = _clip(at, atl - steerDeltaUp, min(atl + steerDeltaDown, steerDeltaUp))

    min_torque = min(abs(max_allowed), abs(min_allowed))
    at = _clip(at, -min_torque, min_torque)
    return i16(at)


def _clip(x, lo, hi):
    return max(lo, min(hi, x))


# =============================================================== SECTION 6
# Delivered surface: what openpilot asks for vs what lands on the wire
# =========================================================================
def delivered_surface(lo=-256, hi=256):
    """For each openpilot apply_steer, encode it the way the fork does and
    decode what the EPS will read. Returns [(commanded, delivered_even,
    delivered_odd)] where even/odd are the two phases of the wiggle bit."""
    out = []
    for cmd in range(lo, hi):
        b1, b0 = op_to_wire_fields(cmd)
        m_even, _ = encode_lkas_to_eps(0, b1, b0, prev_lsb=1)   # wiggle -> 0
        m_odd, _  = encode_lkas_to_eps(1, b1, b0, prev_lsb=0)   # wiggle -> 1
        d_even = wire_fields_to_value(m_even[0] & 0x0F, m_even[1] & 0x1F)
        d_odd  = wire_fields_to_value(m_odd[0] & 0x0F,  m_odd[1] & 0x1F)
        out.append((cmd, d_even, d_odd))
    return out


if __name__ == "__main__":
    print("=" * 72)
    print("1. FRAMING INVARIANT -- can any non-start byte look like a start byte?")
    print("=" * 72)
    bad = []
    for cmd in range(-256, 256):
        b1, b0 = op_to_wire_fields(cmd)
        for prev in (0, 1):
            for cb in (0, 1):
                m, _ = encode_lkas_to_eps(cb, b1, b0, prev)
                if not is_frame_start(m[0]):
                    bad.append(("b0 not a start byte", cmd, m))
                for k in (1, 2, 3):
                    if is_frame_start(m[k]):
                        bad.append((f"b{k} LOOKS LIKE A START BYTE", cmd, m))
    print(f"   frames checked : {512*2*2}")
    print(f"   violations     : {len(bad)}")
    if bad:
        for b in bad[:6]:
            print("     ", b)
    print("   => EVIDENCE: the checksum's %128+128 is what guarantees this.")

    print()
    print("=" * 72)
    print("2. THE WIGGLE BIT -- commanded vs delivered")
    print("=" * 72)
    surf = delivered_surface()
    collisions = {}
    for cmd, de, do in surf:
        collisions.setdefault((de, do), []).append(cmd)
    dupes = {k: v for k, v in collisions.items() if len(v) > 1}
    print(f"   distinct commands in [-256,255] : {len(surf)}")
    print(f"   distinct delivered pairs        : {len(collisions)}")
    print(f"   commands that collide           : {sum(len(v) for v in dupes.values())}")
    print()
    print("   sample around the reported ~230 ceiling:")
    print("     cmd   delivered(even/odd)")
    for cmd, de, do in surf:
        if 226 <= cmd <= 241:
            print(f"     {cmd:4d}   {de:4d} / {do:4d}")

    print()
    print("=" * 72)
    print("3. torque_blend AT REST -- the int8_t truncation")
    print("=" * 72)
    print("   driver_raw is calculate_steer_torque() output, range [0,511],")
    print("   centred near 256 (SECTION 4).")
    print()
    print("   driver_raw  >>1   as int8_t   max_allowed   blend(200,0,raw)")
    for raw in (0, 100, 200, 254, 256, 258, 300, 400, 511):
        dt = i8(raw >> 1)
        dmax = steerMax + (steerDriverAllowance + dt) * steerDriverMultiplier
        dmin = -steerMax + (-steerDriverAllowance + dt) * steerDriverMultiplier
        ma = max(min(steerMax, dmax), 0)
        mi = min(max(-steerMax, dmin), 0)
        allowed = min(abs(ma), abs(mi))
        print(f"   {raw:10d}  {raw>>1:4d}   {dt:9d}   {allowed:11d}   {torque_blend(200, 0, raw):16d}")
    print()
    print("   => the sign of driver_torque flips at raw=256, which is EXACTLY")
    print("      where the wheel sits at rest.")

    print()
    print("=" * 72)
    print("4. RANGE -- is there anything in the FORK that caps near 230?")
    print("=" * 72)
    caps = [("steerMax (common.h)", steerMax),
            ("9-bit wire field max", 255),
            ("9-bit wire field min", -256)]
    for n, v in caps:
        print(f"   {n:28s} {v}")
    print()
    print("   No constant in the fork equals ~230. steerMax is 239.")
    print("   => BELIEF: the ~230 ceiling is enforced by the EPS FIRMWARE,")
    print("      not by this code. That is a firmware question, and it is")
    print("      answerable passively (see the histogram experiment).")
