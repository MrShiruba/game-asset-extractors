"""
PGD files (signature "\\0PGD"): the PSP's encrypted file container (entry 7, read by the
boot module, entry 6). The game hands the system a key with sceIoIoctl(0x04100001) and
the system decrypts the file as it reads it; here it is done in Python, with no key
needed: the "version key" is recovered from the header's MAC.

Layout (little-endian): "\\0PGD", u32 key index, u32 DRM type, u32 0; 0x10 header key;
0x30..0x60 encrypted descriptor (data key, then +0x14 data size, +0x18 block size,
+0x1C data offset); 0x60 MAC of the block table, 0x70 MAC of 0x00..0x70 (gives the
version key), 0x80 MAC of 0x00..0x80 (fixed key); data from 0x90, then one MAC per block.

The crypto is the PSP's security chip (KIRK): AES-128-CBC with fixed keys, a CMAC-like
MAC (BBMac) and a counter mode built on it (BBCipher), as reverse engineered by tpu
(kirk_engine, amctrl.c / pgd.c). AES is written out below so the tool keeps needing no
library; the files are small (1 KB).
"""
import struct

# KIRK command 4 / 7 keys (AES-128) by key slot
_KIRK_KEYS = {
    0x38: bytes.fromhex("12468d7e1c42209bba5426835eb03303"),
    0x39: bytes.fromhex("c43bb6d653ee67493ea95fbc0ced6f8a"),
    0x3A: bytes.fromhex("2cc3cf8c2878a5a663e2af2d715e86ba"),
    0x63: bytes.fromhex("9c9b1372f8c640cf1c62f5d592ddb582"),
}
_MAC_XOR = bytes.fromhex("e350ed1d910a1fd029bb1c3ef34077fb")
_CIPHER_XOR_1 = bytes.fromhex("135fa47cab395ba476b8cca98f3a0445")
_CIPHER_XOR_2 = bytes.fromhex("678d7fa32a9ca0d1508ad8385e4b017e")
_FIXED_KEYS = (bytes.fromhex("ede25d2dbbf812e53c5c5932fae3e243"),    # PGD flag 2
               bytes.fromhex("2774fbeba4a001d702569e338c195783"))    # PGD flag 1

# --- AES-128 -----------------------------------------------------------------------


def _xtime(a):
    return ((a << 1) ^ 0x1B) & 0xFF if a & 0x80 else a << 1


def _mul(a, b):
    r = 0
    while b:
        if b & 1:
            r ^= a
        a, b = _xtime(a), b >> 1
    return r


def _make_sbox():
    sbox, inv = [0] * 256, [0] * 256
    p = q = 1
    while True:
        p = p ^ ((p << 1) & 0xFF) ^ (0x1B if p & 0x80 else 0)      # p * 3
        q ^= q << 1
        q ^= q << 2
        q ^= q << 4
        q &= 0xFF
        if q & 0x80:
            q ^= 0x09                                             # q / 3
        x = q ^ ((q << 1 | q >> 7) & 0xFF) ^ ((q << 2 | q >> 6) & 0xFF) \
            ^ ((q << 3 | q >> 5) & 0xFF) ^ ((q << 4 | q >> 4) & 0xFF) ^ 0x63
        sbox[p] = x
        if p == 1:
            break
    sbox[0] = 0x63
    for i, v in enumerate(sbox):
        inv[v] = i
    return sbox, inv


_SBOX, _INV_SBOX = _make_sbox()


def _expand(key):
    w = [list(key[i:i + 4]) for i in range(0, 16, 4)]
    rcon = 1
    for i in range(4, 44):
        t = list(w[i - 1])
        if i % 4 == 0:
            t = [_SBOX[b] for b in t[1:] + t[:1]]
            t[0] ^= rcon
            rcon = _xtime(rcon)
        w.append([a ^ b for a, b in zip(w[i - 4], t)])
    return [sum(w[4 * r:4 * r + 4], []) for r in range(11)]


def _encrypt_block(rk, block):
    s = [b ^ k for b, k in zip(block, rk[0])]
    for r in range(1, 11):
        s = [_SBOX[b] for b in s]
        s = [s[(i + 4 * (i % 4)) % 16] for i in range(16)]           # shift rows
        if r < 10:
            m = []
            for c in range(4):
                a = s[4 * c:4 * c + 4]
                m += [_mul(a[0], 2) ^ _mul(a[1], 3) ^ a[2] ^ a[3],
                      a[0] ^ _mul(a[1], 2) ^ _mul(a[2], 3) ^ a[3],
                      a[0] ^ a[1] ^ _mul(a[2], 2) ^ _mul(a[3], 3),
                      _mul(a[0], 3) ^ a[1] ^ a[2] ^ _mul(a[3], 2)]
            s = m
        s = [b ^ k for b, k in zip(s, rk[r])]
    return bytes(s)


def _decrypt_block(rk, block):
    s = [b ^ k for b, k in zip(block, rk[10])]
    for r in range(9, -1, -1):
        s = [s[(i - 4 * (i % 4)) % 16] for i in range(16)]           # inverse shift rows
        s = [_INV_SBOX[b] for b in s]
        s = [b ^ k for b, k in zip(s, rk[r])]
        if r:
            m = []
            for c in range(4):
                a = s[4 * c:4 * c + 4]
                m += [_mul(a[0], 14) ^ _mul(a[1], 11) ^ _mul(a[2], 13) ^ _mul(a[3], 9),
                      _mul(a[0], 9) ^ _mul(a[1], 14) ^ _mul(a[2], 11) ^ _mul(a[3], 13),
                      _mul(a[0], 13) ^ _mul(a[1], 9) ^ _mul(a[2], 14) ^ _mul(a[3], 11),
                      _mul(a[0], 11) ^ _mul(a[1], 13) ^ _mul(a[2], 9) ^ _mul(a[3], 14)]
            s = m
    return bytes(s)


_ROUND_KEYS = {}


def _keys(slot):
    if slot not in _ROUND_KEYS:
        _ROUND_KEYS[slot] = _expand(_KIRK_KEYS[slot])
    return _ROUND_KEYS[slot]


def _xor(a, b):
    return bytes(x ^ y for x, y in zip(a, b))


def _cbc_encrypt(slot, data, iv=bytes(16)):          # KIRK command 4
    rk, out, prev = _keys(slot), b"", iv
    for i in range(0, len(data), 16):
        prev = _encrypt_block(rk, _xor(data[i:i + 16], prev))
        out += prev
    return out


def _cbc_decrypt(slot, data, iv=bytes(16)):          # KIRK command 7
    rk, out, prev = _keys(slot), b"", iv
    for i in range(0, len(data), 16):
        block = data[i:i + 16]
        out += _xor(_decrypt_block(rk, block), prev)
        prev = block
    return out


# --- BBMac / BBCipher (amctrl) -----------------------------------------------------


def _double(t):
    n = int.from_bytes(t, "big") << 1
    if t[0] & 0x80:
        n ^= 0x87
    return (n & ((1 << 128) - 1)).to_bytes(16, "big")


def _mac(mac_type, data, version_key=None):
    slot = 0x3A if mac_type == 2 else 0x38
    pad_size = len(data) % 16 or 16
    body, pad = data[:len(data) - pad_size], data[len(data) - pad_size:]
    chain = _cbc_encrypt(slot, body)[-16:] if body else bytes(16)
    sub = _double(_cbc_encrypt(slot, bytes(16)))
    if pad_size < 16:
        sub = _double(sub)
        pad += b"\x80" + bytes(15 - pad_size)
    result = _xor(_cbc_encrypt(slot, _xor(_xor(pad, sub), chain)), _MAC_XOR)
    if version_key:
        result = _cbc_encrypt(slot, _xor(result, version_key))
    return result


def _stored_mac(mac_type, mac):
    return _cbc_decrypt(0x63, mac) if mac_type == 3 else mac


def _cipher(header_key, version_key, data, seed=0):
    key = _xor(header_key, version_key)
    base = _xor(_cbc_decrypt(0x39, _xor(key, _CIPHER_XOR_2)), _CIPHER_XOR_1)
    first = seed + 1
    prev = bytes(16) if first == 1 else base[:12] + struct.pack("<I", first - 1)
    counters = b"".join(base[:12] + struct.pack("<I", first + i) for i in range(len(data) // 16))
    return _xor(data, _cbc_decrypt(0x63, counters, prev))


def decrypt(pgd):
    """Decrypted content of a PGD file, or None (not a PGD, or a MAC does not match)."""
    if len(pgd) < 0x90 or pgd[:4] != b"\0PGD":
        return None
    key_index, drm_type = struct.unpack_from("<II", pgd, 4)
    mac_type = (3 if key_index > 1 else 1) if drm_type == 1 else 2
    if not any(_mac(mac_type, pgd[:0x80], key) == _stored_mac(mac_type, pgd[0x80:0x90])
               for key in _FIXED_KEYS):
        return None
    # version key from the MAC of 0x00..0x70
    slot = 0x3A if mac_type == 2 else 0x38
    version_key = _xor(_mac(mac_type, pgd[:0x70]),
                       _cbc_decrypt(slot, _stored_mac(mac_type, pgd[0x70:0x80])))
    desc = _cipher(pgd[0x10:0x20], version_key, pgd[0x30:0x60])
    size, block, offset = struct.unpack_from("<III", desc, 0x14)
    aligned = (size + 15) & ~15
    if offset + aligned > len(pgd):
        return None
    table = offset + aligned
    blocks = (aligned + block - 1) // block if block else 0
    if _mac(mac_type, pgd[table:table + 16 * blocks], version_key) \
            != _stored_mac(mac_type, pgd[0x60:0x70]):
        return None
    return _cipher(desc[:16], version_key, pgd[offset:offset + aligned])[:size]


def why(pgd):
    """Short reason why decrypt() gives None (for the extraction log)."""
    if len(pgd) < 0x90 or pgd[:4] != b"\0PGD":
        return "not a PGD"
    key_index, drm_type = struct.unpack_from("<II", pgd, 4)
    mac_type = (3 if key_index > 1 else 1) if drm_type == 1 else 2
    if not any(_mac(mac_type, pgd[:0x80], key) == _stored_mac(mac_type, pgd[0x80:0x90])
               for key in _FIXED_KEYS):
        return "header MAC: key index %d, DRM type %d" % (key_index, drm_type)
    return "data MAC or layout"
