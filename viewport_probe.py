"""Isolated RhakMu viewport experiment, NOT a playable release or installer.

The installed executable and multiplayer patches are never modified. The source
hash identifies the local, already network-patched 1.000d build, not a pristine
retail executable. Only individually inspected instructions are changed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct

SOURCE_HASHES = {
    'Rhakmu.exe': 'ef006b8b3a5319279e4313e6faed873ca655082643cb79535d81f05804306d16',
    'iCARUS.dll': '1783757a0091d18cbf53a65e5c42bc07a4ef245020bf7a7716865fa520969b2e',
    'GameCtrl.dll': '97a69db96bdf1271b7c902446f6f6d91d53b3e751be0ec1a492b28bce7072e88',
}

# classSCREEN::Main_SetWindowRect large-mode block. Generated from individually
# disassembled instructions, no new PE section and no networking cave reuse.
HIGHMODE_ORIGINAL = bytes.fromhex(
    '8b55fcc782b0000000700000000fbf05e2a506012db90000008b4dfc8981b4000000'
    '0fbf15e0a5060183ea718b45fc8990b80000000fbf0de2a5060183e9018b55fc898abc000000'
    'c70504a6060100000000c7050ca6060100040000c70508a6060100000000c70510a6060100030000'
    '8b45fcc7400401000000')
HIGHMODE_CODE = bytes.fromhex(
    '8b55fc0fbf022d20030000d1f88982b000000066a3a01e5000051f0300008982b8000000'
    '0fbf42022db90000008982b400000005b80000008982bc0000002d5702000066a3a21e5000'
    '31c0a304a60601a308a606010fbf02a30ca606010fbf4202a310a60601c7420401000000')


def transform(source, width=1280, height=720):
    if (width, height) != (1280, 720):
        raise ValueError('Only the first 1280x720 research stage is enabled')
    if hashlib.sha256(source).hexdigest() != SOURCE_HASHES['Rhakmu.exe']:
        raise ValueError('Unknown executable SHA-256; refusing to patch')
    data = bytearray(source)
    edits = []

    def replace(va, before, after, reason):
        offset = va - 0x400000  # verified .text RVA == file offset in this hash
        if len(before) != len(after) or data[offset:offset + len(before)] != before:
            raise ValueError(f'Instruction mismatch at {va:#x}')
        data[offset:offset + len(after)] = after
        edits.append(dict(va=hex(va), before=before.hex(), after=after.hex(), reason=reason))

    # Initial, logo and post-game menu scenes MUST retain 1024x768; their assets
    # do not fit 720px height. Change only the in-game high-resolution option.
    for va in (0x45aebf,):
        replace(va, b'\x68\x00\x03\x00\x00\x68\x00\x04\x00\x00',
                b'\x68' + struct.pack('<I', height) + b'\x68' + struct.pack('<I', width),
                'in-game high-resolution option request')
    # CGameMenu::Menu_GameBeforeProcess normally forces 800x600. Apply on entry,
    # without relying on the in-game option event (which is gated in some modes).
    for va in (0x4237f8, 0x423821):
        replace(va, bytes.fromhex('68580200006820030000'),
                b'\x68' + struct.pack('<I', height) + b'\x68' + struct.pack('<I', width),
                'battle entry resolution, not lobby/logo/result scenes')
    # Dynamic clip and centered 800px HUD. Update the shared large-mode origin
    # table used by panel buttons/minimap together with the panel rectangle.
    replace(0x4dc3fa, HIGHMODE_ORIGINAL,
            HIGHMODE_CODE + b'\x90' * (len(HIGHMODE_ORIGINAL)-len(HIGHMODE_CODE)),
            'dynamic full clip, centered HUD container and shared child origin')
    from viewport_helpers import helpers, RECTS, INIT_RETURN, CURSOR_RETURN, LEFT_DECORATION
    # The existing network patch already maps the entire .text raw allocation.
    if source[0x208:0x20c] != struct.pack('<I', 0xeb000):
        raise ValueError('Unexpected .text virtual size; helper addresses are not safe')
    for va, code in helpers().items():
        if len(code) > 256:
            raise ValueError('Helper exceeds its reserved region')
        replace(va, bytes(len(code)), code, 'viewport UI helper in verified zero padding')

    def jump(va, target, original, reason):
        replace(va, original, b'\xe9'+struct.pack('<i', target-va-5)+b'\x90'*(len(original)-5), reason)

    jump(0x45bab0, RECTS, bytes.fromhex('558bec83ec44535657894dfc5f5e5b8be55dc3'),
         'refresh command images AND hit rectangles on resolution change')
    jump(0x45bc0e, INIT_RETURN, bytes.fromhex('5f5e5b8be55dc3'),
         'initialize command rectangles using current HUD origin, not startup coordinates')
    jump(0x4d664c, CURSOR_RETURN, bytes.fromhex('5f5e5b8be55dc3'),
         'restore software cursor background after presenting each full frame')
    jump(0x464772, LEFT_DECORATION, bytes.fromhex('668b54010252'),
         'attach left 112px decoration to centered panel instead of screen edge')
    return bytes(data), edits


def build(source_dir, destination):
    source_dir, destination = Path(source_dir).resolve(), Path(destination).resolve()
    allowed = Path(__file__).resolve().parent / 'research' / 'runtime'
    if destination.parent != allowed or destination.exists():
        raise ValueError('Destination must be a NEW directory directly in research/runtime')
    if source_dir == destination or source_dir in destination.parents:
        raise ValueError('Refusing to write inside the installation')
    for name, expected in SOURCE_HASHES.items():
        if hashlib.sha256((source_dir / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f'Unsupported {name}; nothing written')
    output, edits = transform((source_dir / 'Rhakmu.exe').read_bytes())
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_dir, destination, ignore=shutil.ignore_patterns('*.bak*', '*.ERR', '*.LOG', '*.log'))
    shutil.copy2(destination / 'Rhakmu.exe', destination / 'Rhakmu.exe.original')
    (destination / 'Rhakmu.exe').write_bytes(output)
    from display_settings import update_section
    # Preserve the existing compatibility/timing flags (especially maxgameticks)
    # so the experiment does not introduce an unrelated timing change.
    ini = (source_dir / 'ddraw.ini').read_bytes().decode('utf-8-sig')
    ini = update_section(ini, dict(width=0, height=0, windowed='true', fullscreen='false',
                                  maintas='true', savesettings=0, adjmouse='true', devmode='false',
                                  resizable='false', posX=-32000, posY=-32000))
    (destination / 'ddraw.ini').write_text(ini, encoding='utf-8')
    report = dict(diagnostic_only=True, source_hashes=SOURCE_HASHES, edits=edits,
                  output_sha256=hashlib.sha256(output).hexdigest(),
                  unverified=['HUD children', 'terrain partial bottom tile', 'all object collectors',
                              'cursor', 'audio', 'IME', 'performance', 'multiplayer'])
    (destination / 'viewport-manifest.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    print(build(args.source, args.destination))
