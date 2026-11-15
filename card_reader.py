"""Read Koikatsu card envelopes without executing embedded data."""
import hashlib
import struct
import msgpack
from pathlib import Path


def inspect_card(path):
    data = Path(path).read_bytes()
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('Not a PNG file')
    offset = 8
    while True:
        if offset + 12 > len(data):
            raise ValueError('Truncated PNG')
        size = struct.unpack_from('>I', data, offset)[0]
        kind = data[offset + 4:offset + 8]
        offset += size + 12
        if offset > len(data):
            raise ValueError('PNG chunk exceeds file')
        if kind == b'IEND':
            break
    payload = data[offset:]
    if b'KoiKatuChara' not in payload[:80]:
        raise ValueError('PNG has no supported Koikatsu character-card payload')
    cursor = offset + 4
    def read_string():
        nonlocal cursor
        length, shift = 0, 0
        for _ in range(5):
            if cursor >= len(data): raise ValueError('Truncated card string')
            byte = data[cursor]; cursor += 1
            length |= (byte & 127) << shift
            if byte < 128: break
            shift += 7
        else: raise ValueError('Invalid string length')
        if cursor + length > len(data): raise ValueError('Card string exceeds file')
        value = data[cursor:cursor+length].decode('utf-8')
        cursor += length
        return value
    marker, version = read_string(), read_string()
    if marker not in ('【KoiKatuChara】', '【KoiKatuCharaSun】'): raise ValueError('Unsupported card marker')
    preview_size = struct.unpack_from('<i', data, cursor)[0]
    cursor += 4 + preview_size
    if preview_size < 0 or cursor + 4 > len(data):
        raise ValueError('Invalid card preview size')
    header_size = struct.unpack_from('<i', data, cursor)[0]; cursor += 4
    if header_size < 0 or cursor + header_size + 8 > len(data):
        raise ValueError('Invalid card block header')
    blocks = msgpack.unpackb(data[cursor:cursor+header_size], raw=False)['lstInfo']
    cursor += header_size + 8
    plugins = []
    for block in blocks:
        start, size = block['pos'], block['size']
        if start < 0 or size < 0 or cursor + start + size > len(data):
            raise ValueError('Card block exceeds file')
        if block['name'] == 'KKEx':
            extra = msgpack.unpackb(data[cursor+start:cursor+start+size], raw=False, strict_map_key=False)
            plugins = sorted(extra) if isinstance(extra, dict) else []
    return {'type': 'koikatsu_card', 'name': Path(path).name,
            'sha256': hashlib.sha256(data).hexdigest(), 'png_bytes': offset,
            'payload_bytes': len(payload), 'requires_game_assembly': True,
            'format': marker, 'version': version, 'blocks': blocks, 'plugins': plugins,
            'note': 'Card parameters require Koikatsu and matching Sideloader assets; PNG pixels are not mesh geometry.'}
