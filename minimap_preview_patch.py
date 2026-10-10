"""Offline terrain-only minimap preview prototype for verified RhakMu binaries.

No installation or release. Does not yet implement resource/entrance markers.
Existing cached 128x128 RGB16 terrain replaces explored-terrain copy source.
Enemy unit/structure visibility paths and simulation data are not patched.
"""
import argparse
from pathlib import Path
import viewport_patch

OFFSET = 0x67754
BEFORE = bytes.fromhex('052c800000')
AFTER = bytes.fromhex('052c000000')


def transform(data, enabled=True):
    current = data[OFFSET:OFFSET+len(BEFORE)]
    if current not in (BEFORE, AFTER):
        raise ValueError('Unsupported minimap InitViewMap instructions')
    normalized = data[:OFFSET] + BEFORE + data[OFFSET+len(BEFORE):]
    # Full-image allowlist, including the known viewport and independent patches.
    viewport_patch.transform(normalized, False)
    return data[:OFFSET] + (AFTER if enabled else BEFORE) + data[OFFSET+len(BEFORE):]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--restore', action='store_true')
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error('Use a separate output file; installed game is never overwritten')
    result = transform(args.source.read_bytes(), not args.restore)
    with args.output.open('xb') as stream:
        stream.write(result)
    print('Terrain-only trial created. Resource/entrance markers not implemented.')
