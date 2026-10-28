"""Internal extended Windows paths; user-facing paths still pass normal whitelist validation."""
import os


def native_path(path):
    raw=os.fspath(path)
    if os.name=='nt' and os.path.isabs(raw) and not raw.startswith('\\\\?\\'):
        return '\\\\?\\'+raw
    return raw


def display_path(path):
    raw=os.fspath(path)
    return raw[4:] if os.name=='nt' and raw.startswith('\\\\?\\') else raw
