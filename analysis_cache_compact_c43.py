"""C43: compact storage for *recreatable* Spot analysis cache entries.

The canonical result and the published/persisted signals are never altered.
Packing uses a lossless pickle protocol so existing nested python/pandas types
survive (unlike lossy JSON). A failed/inefficient pack uses the legacy deepcopy.
Only trusted results created by this process are packed; never unpickle user input.
"""
from __future__ import annotations

from copy import deepcopy
import io
import pickle
import zlib

# Don't spend CPU packing small cards or building huge serializations.
MIN_RAW_BYTES = 128 * 1024
MAX_RAW_BYTES = 8 * 1024 * 1024
MIN_SAVING_RATIO = 0.75


class _TooLargeToPack(Exception):
    pass


class _BoundedPickleBuffer(io.BytesIO):
    """Stop serializing before transient serialization exceeds 8 MiB."""
    def write(self, block):
        if self.tell() + len(block) > MAX_RAW_BYTES:
            raise _TooLargeToPack()
        return super().write(block)


def pack_cache_entry(data, enabled=True):
    """Return a cache slot with unchanged logical content and copy isolation."""
    if enabled:
        try:
            stream = _BoundedPickleBuffer()
            pickle.Pickler(stream, protocol=pickle.HIGHEST_PROTOCOL).dump(data)
            raw = stream.getvalue()
            if len(raw) >= MIN_RAW_BYTES:
                compressed = zlib.compress(raw, level=1)
                if len(compressed) <= len(raw) * MIN_SAVING_RATIO:
                    return {'packed': compressed, 'raw_bytes': len(raw)}
        except (Exception,):
            # Pickle cannot represent all technical objects (e.g. closures).
            # Preserve the old exact deepcopy behavior if that happens.
            pass
    return {'data': deepcopy(data)}


def read_cache_entry(entry, *, isolated=False):
    """Decode a C43 packed slot, or read a legacy slot without changing it.

    `isolated=True` is the public cache-get contract: callers may modify the
    result but can never modify another user's shared cache.
    """
    if not isinstance(entry, dict):
        return None
    packed = entry.get('packed')
    if isinstance(packed, bytes):
        try:
            # Trusted in-process objects only. Decompression recreates a new
            # independent object graph each time, so deepcopy is unnecessary.
            return pickle.loads(zlib.decompress(packed))
        except Exception:
            return None
    data = entry.get('data')
    return deepcopy(data) if isolated else data


def compact_cache_statistics(cache):
    entries = [item for item in cache.values() if isinstance(item, dict)]
    packed = [item for item in entries if isinstance(item.get('packed'), bytes)]
    return {
        'packed_entries': len(packed),
        'packed_bytes': sum(len(item['packed']) for item in packed),
        'uncompressed_bytes': sum(int(item.get('raw_bytes') or 0) for item in packed),
    }
