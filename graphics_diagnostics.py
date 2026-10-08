"""Read-only, explicit-PID graphics probe for the researched RhakMu executable.

No injection, writes, credentials, command lines, or per-frame file logging.
"""
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import struct


def snapshot(pid):
    from viewport_probe import SOURCE_HASHES, transform
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.ReadProcessMemory.argtypes = (wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                        ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t))
    kernel.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE, wintypes.DWORD,
                                                wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
    handle = kernel.OpenProcess(0x1010, False, pid)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        path_buffer = ctypes.create_unicode_buffer(32768)
        length = wintypes.DWORD(len(path_buffer))
        if not kernel.QueryFullProcessImageNameW(handle, 0, path_buffer, ctypes.byref(length)):
            raise ctypes.WinError(ctypes.get_last_error())
        path = Path(path_buffer.value)
        if path.name.lower() != 'rhakmu.exe':
            raise ValueError('Only Rhakmu.exe is supported')
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        allowed = {SOURCE_HASHES['Rhakmu.exe']}
        backup = path.with_name('Rhakmu.exe.original')
        if backup.exists() and hashlib.sha256(backup.read_bytes()).hexdigest() in allowed:
            allowed.add(hashlib.sha256(transform(backup.read_bytes())[0]).hexdigest())
        if digest not in allowed:
            raise ValueError('Unknown executable; refusing to interpret fixed addresses')

        def read(address, fmt):
            size = struct.calcsize(fmt)
            buffer = ctypes.create_string_buffer(size)
            count = ctypes.c_size_t()
            if not kernel.ReadProcessMemory(handle, address, buffer, size, ctypes.byref(count)) or count.value != size:
                raise ctypes.WinError(ctypes.get_last_error())
            values = struct.unpack(fmt, buffer.raw)
            return values[0] if len(values) == 1 else list(values)

        tag = read(0x4ec438, '<I')
        view_slot = read(0xb412cd, '<b')
        camera = read(0xb412d8 + view_slot*2, '<hh') if 0 <= view_slot < 8 else None
        return dict(pid=pid, executable_sha256=digest,
                    screen=read(0x106a5e0, '<hh'),
                    full_clip=read(0x106a604, '<iiii'),
                    hud_container=read(0x106a690, '<iiii'),
                    color_format=read(0x106a638, '<I'),
                    requested_color_bits=read(tag + 0x5c, '<B'),
                    surface_dimensions=read(tag + 0x5e, '<hh'),
                    virtual_dimensions=read(tag + 0x62, '<hh'),
                    byte_pitch=read(tag + 0x68, '<i'),
                    pixel_pitch=read(tag + 0x6c, '<i'),
                    view_slot=view_slot, camera_tiles=camera,
                    map_dimensions=read(0xb412d4, '<hh'),
                    note='Single read-only snapshot, not a performance benchmark; fields may change during scene transitions')
    finally:
        kernel.CloseHandle(handle)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pid', type=int)
    print(json.dumps(snapshot(parser.parse_args().pid), indent=2))
