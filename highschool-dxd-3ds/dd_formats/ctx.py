"""CTX textures (header + PICA200 data) -> RGBA image as a numpy array."""
import struct

import numpy as np

ETC_MOD_L = ([[2, 8, -2, -8], [5, 17, -5, -17], [9, 29, -9, -29], [13, 42, -13, -42],
                    [18, 60, -18, -60], [24, 80, -24, -80], [33, 106, -33, -106], [47, 183, -47, -183]])
ETC_MOD = np.array(ETC_MOD_L, dtype=np.int32)

FORMATS = {  # (GL format, GL type) -> name
    (0x675A, None): 'ETC1', (0x675B, None): 'ETC1A4',
    (0x1908, 0x1401): 'RGBA8', (0x1908, 0x8033): 'RGBA4', (0x1908, 0x8034): 'RGBA5551',
    (0x1907, 0x1401): 'RGB8', (0x1907, 0x8363): 'RGB565',
    (0x190A, 0x1401): 'LA8', (0x190A, 0x6760): 'LA4', (0x1909, 0x1401): 'L8',
    (0x1909, 0x6761): 'L4', (0x1906, 0x1401): 'A8', (0x1906, 0x6761): 'A4',
}
# 3DS "native" (DMP) format constants: same pixel layouts as the GL ones above
for _gl, _dmp in ((0x1908, 0x6752), (0x1907, 0x6754), (0x1906, 0x6756), (0x1909, 0x6757), (0x190A, 0x6758)):
    for (_f, _t), _n in list(FORMATS.items()):
        if _f == _gl:
            FORMATS[(_dmp, _t)] = _n


def parse_header(d):
    if d[:4] != b'CTX ':
        raise ValueError('not a CTX file')
    w, h, w2, h2, target, fmt, typ, size = struct.unpack_from('<8I', d, 8)
    name = FORMATS.get((fmt, None)) or FORMATS.get((fmt, typ))
    return dict(w=w, h=h, w2=w2, h2=h2, fmt=fmt, typ=typ, size=size, name=name)


def _ext5(v):
    return (v << 3) | (v >> 2)


def _etc1_blocks(col):
    """col : uint64 (N,) -> pixels (N, 4, 4, 3) indexed [block, y, x]."""
    hi = (col >> np.uint64(32)).astype(np.int64)
    lo = (col & np.uint64(0xFFFFFFFF)).astype(np.int64)
    diff = (hi >> 1) & 1
    flip = hi & 1
    t1 = (hi >> 5) & 7
    t2 = (hi >> 2) & 7
    c1 = np.zeros((len(col), 3), np.int64); c2 = np.zeros_like(c1)
    for k, sh in enumerate((27, 19, 11)):
        b5 = (hi >> sh) & 31
        d3 = (hi >> (sh - 3)) & 7
        d3 = np.where(d3 >= 4, d3 - 8, d3)
        b4a = (hi >> (sh + 1)) & 15
        b4b = (hi >> (sh - 3)) & 15
        c1[:, k] = np.where(diff == 1, _ext5(b5), b4a * 17)
        c2[:, k] = np.where(diff == 1, _ext5((b5 + d3) & 31), b4b * 17)
    out = np.zeros((len(col), 4, 4, 3), np.int64)
    for x in range(4):
        for y in range(4):
            i = x * 4 + y
            idx = (((lo >> (i + 16)) & 1) << 1) | ((lo >> i) & 1)
            second = np.where(flip == 1, y >= 2, x >= 2)
            base = np.where(second[:, None], c2, c1)
            tab = np.where(second, t2, t1)
            out[:, y, x, :] = np.clip(base + ETC_MOD[tab, idx][:, None], 0, 255)
    return out.astype(np.uint8)


def _untile(blocks, w, h, bs):
    """blocks (N, bs, bs, C) in 3DS order (8x8 tiles, Z-order) -> image (h, w, C)."""
    C = blocks.shape[-1]
    img = np.zeros((h, w, C), np.uint8)
    per = 8 // bs
    n = 0
    for ty in range(0, h, 8):
        for tx in range(0, w, 8):
            for by in range(per):
                for bx in range(per):
                    y, x = ty + by * bs, tx + bx * bs
                    img[y:y+bs, x:x+bs] = blocks[n]; n += 1
    return img


def _morton_untile(px, w, h):
    """px (w*h, C) in 3DS order (8x8 tiles, Morton-ordered pixels) -> image (h, w, C)."""
    m = np.zeros(64, np.int64)
    for i in range(64):
        x = (i & 1) | ((i >> 1) & 2) | ((i >> 2) & 4)
        y = ((i >> 1) & 1) | ((i >> 2) & 2) | ((i >> 3) & 4)
        m[i] = y * 8 + x
    C = px.shape[-1]
    tiles = px.reshape(-1, 64, C)
    img = np.zeros((h // 8, w // 8, 64, C), np.uint8)
    img[:, :, m] = tiles.reshape(h // 8, w // 8, 64, C)
    return img.reshape(h // 8, w // 8, 8, 8, C).transpose(0, 2, 1, 3, 4).reshape(h, w, C)


def decode(d):
    hd = parse_header(d)
    w, h, name = hd['w'], hd['h'], hd['name']
    data = np.frombuffer(d, np.uint8, offset=0x40)
    if name in ('ETC1', 'ETC1A4'):
        nb = w * h // 16
        if name == 'ETC1':
            col = data[:nb * 8].view('<u8')
            alpha = None
        else:
            raw = data[:nb * 16].view('<u8').reshape(nb, 2)
            alpha, col = raw[:, 0], raw[:, 1]
        rgb = _etc1_blocks(col)
        a = np.full((nb, 4, 4, 1), 255, np.uint8)
        if alpha is not None:
            for x in range(4):
                for y in range(4):
                    v = ((alpha >> np.uint64(4 * (x * 4 + y))) & np.uint64(15)).astype(np.uint8)
                    a[:, y, x, 0] = v * 17
        img = _untile(np.concatenate([rgb, a], -1), w, h, 4)
    else:
        n = w * h
        if name == 'RGBA8':
            p = data[:n*4].reshape(n, 4)[:, ::-1]
        elif name == 'RGB8':
            p = np.concatenate([data[:n*3].reshape(n, 3)[:, ::-1], np.full((n, 1), 255, np.uint8)], 1)
        elif name in ('RGBA4', 'RGBA5551', 'RGB565'):
            v = data[:n*2].view('<u2').astype(np.uint32)
            if name == 'RGBA4':
                ch = [(v >> s) & 15 for s in (12, 8, 4, 0)]; p = np.stack(ch, 1) * 17
            elif name == 'RGBA5551':
                ch = [_ext5((v >> s) & 31) for s in (11, 6, 1)] + [(v & 1) * 255]; p = np.stack(ch, 1)
            else:
                p = np.stack([_ext5((v >> 11) & 31), ((v >> 5) & 63) << 2 | ((v >> 5) & 63) >> 4,
                              _ext5(v & 31), np.full(n, 255)], 1)
            p = p.astype(np.uint8)
        elif name == 'LA8':
            la = data[:n*2].reshape(n, 2); L, A = la[:, 1], la[:, 0]
            p = np.stack([L, L, L, A], 1)
        elif name == 'L8':
            L = data[:n]; p = np.stack([L, L, L, np.full(n, 255, np.uint8)], 1)
        elif name == 'A8':
            A = data[:n]; p = np.stack([np.full(n, 255, np.uint8)] * 3 + [A], 1)
        elif name == 'LA4':
            v = data[:n]; L, A = (v >> 4) * 17, (v & 15) * 17; p = np.stack([L, L, L, A], 1).astype(np.uint8)
        elif name in ('L4', 'A4'):
            v = data[:n // 2]; q = np.stack([v & 15, v >> 4], 1).reshape(-1)[:n] * 17
            q = q.astype(np.uint8)
            p = np.stack([q, q, q, np.full(n, 255, np.uint8)], 1) if name == 'L4' else \
                np.stack([np.full(n, 255, np.uint8)] * 3 + [q], 1)
        else:
            raise ValueError('unknown format fmt=0x%x type=0x%x' % (hd['fmt'], hd['typ']))
        img = _morton_untile(p, w, h)
    # unlike most 3DS games, this one stores textures upright: no vertical flip
    return img, hd
