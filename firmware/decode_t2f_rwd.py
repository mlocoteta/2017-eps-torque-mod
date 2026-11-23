"""Decode a 9th-gen Accord (T2F/T3L family) Honda EPS .rwd to a plain V850 image.

Reproduces analysis-2017accord/firmware/39990-T2F-L310_plain_image.bin from the
dealer container 39990-T2F-L310.rwd.

WHAT THIS IS (EVIDENCE, 2026-11-23)
-----------------------------------
The .rwd is Honda's x31 reflash container. Its payload is a byte-substitution
cipher: plain = decode_table[cipher]. decode_table[i] = (((i op1 k1) op2 k2) op3 k3)
& 0xFF for a 3-byte key and 3 ops. The key is in the file's '&' header (BF109E).

THE AMBIGUITY TRAP (read before trusting any decode)
----------------------------------------------------
Cracking by "the part-number string must appear in the plaintext" is NOT enough.
Two DIFFERENT 256-byte tables both decode the 14-byte part string to
'39990-T2F-L310' while diverging on the code bytes:

    A: ((i - 0x9e) + 0xbf) ^ 0x10      <- the cracker's matches[0], WRONG (decoy)
    B: ((i - 0x9e) ^ 0x10) + 0xbf      <- CORRECT

They are separated by the PADDING byte, not the part string. Honda pads programmed
blocks to 128-byte boundaries with erased-flash 0xFF. Under B the 2nd-most-common
plaintext byte is 0xFF (3.76%); under A it is 0x1F (0xFF falls to 0.15%, physically
impossible for 210 KB of firmware). The ID block confirms it: under B the part
string is followed by clean 0xFF padding; under A, by 0x1F garbage.

=> Always disambiguate a freshly cracked Honda table by the padding byte, then
   eyeball the ID block. This script hardcodes table B and re-derives it so the
   reasoning is reproducible.

Usage:  python -I decode_t2f_rwd.py <path-to.rwd> [out_dir]
        (run -I: the .rwd is untrusted downloaded data)
"""
import sys, os, hashlib, operator
from binascii import a2b_hex
from collections import Counter

# --- the correct cipher, stated two ways and asserted equal ---
KEY = (0x9e, 0x10, 0xbf)
OPS = (operator.sub, operator.xor, operator.add)   # ((i - 0x9e) ^ 0x10) + 0xbf


def build_table(keys, ops):
    (k1, k2, k3) = keys
    (o1, o2, o3) = ops
    t = bytearray(256)
    for i in range(256):
        t[i] = o3(o2(o1(i, k1) & 0xFF, k2) & 0xFF, k3) & 0xFF
    assert len(set(t)) == 256, "cipher table is not a bijection"
    return bytes(t)


def parse_x31(data):
    """Honda x31 container -> (key_bytes, blocks, enc_blocks). Blocks are dicts
    {'start','length'}; address units are 16 bytes ((hi<<12)|(mid<<4))."""
    assert data[0:1] == b'1', "not an x31 container"
    i = 3
    headers = []
    for _ in range(6):
        hp = data[i:i + 3]
        i += 3
        vals = []
        while data[i:i + 3] != hp:
            end = data.find(b'\x0d\x0a', i)
            vals.append(data[i:end])
            i = end + 2
        i += 3
        headers.append((hp[0:1], vals))
    key = None
    for hid, vals in headers:
        if hid == b'&':
            key = a2b_hex(vals[0])
    fw = data[i:-4]
    chunk, ds = 130, 128
    blocks, encs = [], []
    an = bs = 0
    bd = b''
    for j in range(0, len(fw) - chunk + 1, chunk):
        addr = (fw[j] << 12) | (fw[j + 1] << 4)
        if addr != an:
            if bd:
                blocks.append({'start': bs, 'length': len(bd)})
                encs.append(bd)
            bs, bd = addr, b''
        bd += fw[j + 2:j + 2 + ds]
        an = addr + ds
    if bd:
        blocks.append({'start': bs, 'length': len(bd)})
        encs.append(bd)
    return list(key), blocks, encs, headers


FLASH_SIZE = 0x3C000   # uPD70F3413 code flash 0x0..0x3BFFF = 240 KB (device file DF3413.800)


def main():
    path = sys.argv[1]
    outdir = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(os.path.abspath(__file__))
    raw = open(path, 'rb').read()
    key, blocks, encs, headers = parse_x31(raw)

    table = build_table(KEY, OPS)
    decoded = [b.translate(table) for b in encs]

    # --- self-checks that prove the table is the right one, not the decoy ---
    allp = b''.join(decoded)
    hist = Counter(allp)
    assert b'39990-T2F-L310' in allp, "part string absent -- wrong family/key"
    # 0xFF must be a real population (erased/padding); the decoy drops it to ~0.15%
    ff_pct = 100 * hist[0xFF] / len(allp)
    assert ff_pct > 1.0, f"0xFF only {ff_pct:.2f}% -- this is the decoy table"

    img = bytearray(b'\xff' * FLASH_SIZE)
    for b, d in zip(blocks, decoded):
        img[b['start']:b['start'] + len(d)] = d
    out = os.path.join(outdir, "39990-T2F-L310_plain_image.bin")
    open(out, 'wb').write(img)

    print(f"source : {path}  ({len(raw)} bytes)")
    print(f"cipher : ((i - 0x9e) ^ 0x10) + 0xbf   key(hdr '&')={''.join(f'{k:02x}' for k in key)}")
    print(f"image  : {out}")
    print(f"size   : 0x{FLASH_SIZE:X} ({FLASH_SIZE})   base 0x0")
    print(f"sha256 : {hashlib.sha256(img).hexdigest()}")
    prog = sum(b['length'] for b in blocks)
    print(f"programmed: {prog} bytes (0x{prog:X}) = {100 * prog / FLASH_SIZE:.1f}% of 240 KB")
    print(f"0xFF population: {ff_pct:.2f}%  (decoy would be ~0.15%)")


if __name__ == "__main__":
    main()
