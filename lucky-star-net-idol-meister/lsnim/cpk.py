"""CRI CPK archives: @UTF tables, CRILAYLA decompression, file list."""
import os
import struct


def decrypt_utf(data):
    data = bytearray(data)
    mask = 0x655f
    for i in range(len(data)):
        data[i] ^= mask & 0xff
        mask = (mask * 0x4115) & 0xffffffff
    return bytes(data)


def read_utf(data):
    if data[:4] != b'@UTF':
        data = decrypt_utf(data)
    if data[:4] != b'@UTF':
        raise ValueError('invalid @UTF table')
    (_size, rows_offset, strings_offset, data_offset, _name_offset,
     num_columns, row_length, num_rows) = struct.unpack('>IIIIIHHI', data[4:32])
    base = 8

    def read_string(offset):
        offset += base + strings_offset
        return data[offset:data.index(b'\0', offset)].decode('cp932', 'replace')

    formats = {0: '>B', 1: '>b', 2: '>H', 3: '>h', 4: '>I', 5: '>i', 6: '>Q', 7: '>q', 8: '>f'}

    def read_value(value_type, pos):
        if value_type in formats:
            fmt = formats[value_type]
            return struct.unpack_from(fmt, data, pos)[0], struct.calcsize(fmt)
        if value_type == 0xa:
            return read_string(struct.unpack_from('>I', data, pos)[0]), 4
        if value_type == 0xb:
            offset, size = struct.unpack_from('>II', data, pos)
            start = base + data_offset + offset
            return data[start:start + size], 8
        raise ValueError('unknown column type %x' % value_type)

    columns = []
    pos = 32
    for _ in range(num_columns):
        flags = data[pos]
        name = read_string(struct.unpack_from('>I', data, pos + 1)[0])
        pos += 5
        storage, value_type = flags & 0xf0, flags & 0x0f
        constant = None
        if storage == 0x30:                      # constant value stored in the schema
            constant, length = read_value(value_type, pos)
            pos += length
        columns.append((name, storage, value_type, constant))

    rows = []
    for row_index in range(num_rows):
        pos = base + rows_offset + row_index * row_length
        row = {}
        for name, storage, value_type, constant in columns:
            if storage == 0x50:                  # per-row value
                row[name], length = read_value(value_type, pos)
                pos += length
            elif storage == 0x30:
                row[name] = constant
            else:                                # zero / unused column
                row[name] = None
        rows.append(row)
    return rows


# ---------------------------------------------------------------- CRILAYLA

def decompress_crilayla(src):
    if src[:8] != b'CRILAYLA':
        return src
    uncompressed_size, header_offset = struct.unpack_from('<II', src, 8)
    out = bytearray(uncompressed_size + 0x100)
    out[:0x100] = src[0x10 + header_offset:0x10 + header_offset + 0x100]  # raw 0x100-byte header

    input_pos = 0x10 + header_offset - 1        # data is read backwards
    output_end = 0x100 + uncompressed_size - 1
    bit_pool = 0
    bits_left = 0
    written = 0

    def get_bits(count):
        nonlocal bit_pool, bits_left, input_pos
        while bits_left < count:
            bit_pool = ((bit_pool << 8) | src[input_pos]) & 0xffffffff
            input_pos -= 1
            bits_left += 8
        bits_left -= count
        return (bit_pool >> bits_left) & ((1 << count) - 1)

    length_bits = (2, 3, 5, 8)
    while written < uncompressed_size:
        if get_bits(1):                          # back-reference
            ref_pos = output_end - written + get_bits(13) + 3
            ref_length = 3
            for bit_count in length_bits:
                value = get_bits(bit_count)
                ref_length += value
                if value != (1 << bit_count) - 1:
                    break
            else:
                while True:
                    value = get_bits(8)
                    ref_length += value
                    if value != 255:
                        break
            for _ in range(ref_length):
                out[output_end - written] = out[ref_pos]
                ref_pos -= 1
                written += 1
        else:                                    # literal byte
            out[output_end - written] = get_bits(8)
            written += 1
    return bytes(out)




def read_table(f, offset, magic):
    f.seek(offset)
    header = f.read(16)
    if header[:4] != magic:
        raise ValueError('expected %r at 0x%x, got %r' % (magic, offset, header[:4]))
    size = struct.unpack_from('<Q', header, 8)[0]
    return read_utf(f.read(size))


def list_entries(f):
    """Return a list of (name, offset, stored_size)."""
    cpk_header = read_table(f, 0, b'CPK ')[0]
    toc_offset = cpk_header.get('TocOffset') or 0
    content_offset = cpk_header.get('ContentOffset') or 0
    align = cpk_header.get('Align') or 1
    entries = []
    if toc_offset:                               # archive with file names
        base = min(toc_offset, content_offset) if content_offset else toc_offset
        for row in read_table(f, toc_offset, b'TOC '):
            name = os.path.join(row.get('DirName') or '', row['FileName'])
            entries.append((name, row['FileOffset'] + base, row['FileSize']))
    elif cpk_header.get('ItocOffset'):           # ID-only archive: files stored in ID order
        itoc = read_table(f, cpk_header['ItocOffset'], b'ITOC')[0]
        files = []
        for key in ('DataL', 'DataH'):
            if itoc.get(key):
                for row in read_utf(itoc[key]):
                    files.append((row['ID'], row['FileSize']))
        files.sort()
        offset = content_offset
        for file_id, size in files:
            entries.append(('%05d.bin' % file_id, offset, size))
            offset += size
            if size % align:
                offset += align - size % align
    else:
        raise ValueError('no TOC or ITOC found')
    return entries
