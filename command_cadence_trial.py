"""Offline, opt-in experiment: retain four batches, seal every three frames.

Never edits the input, installed game, launcher manifest or live process.
Both peers must use the same experiment. Not a verified multiplayer release.
"""
import argparse
import hashlib
from pathlib import Path
import viewport_patch

OFFSET = 0xD7B96
BEFORE = bytes.fromhex('b905000000')
AFTER = bytes.fromhex('b903000000')
BUFFER_OFFSET = 0xD7ABE


def transform(data):
    # Reuse the official whole-image allowlist, normalizing viewport only for
    # validation. Preserve the actual viewport and independent resource patch.
    viewport_patch.transform(data, False)
    if data[OFFSET:OFFSET + 5] != BEFORE:
        raise ValueError('Unsupported command scheduler')
    if data[BUFFER_OFFSET] != 4:
        raise ValueError('This experiment requires the existing four-turn setting')
    result = bytearray(data)
    result[OFFSET:OFFSET + 5] = AFTER
    return bytes(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error('Output must be a separate trial file')
    source = args.source.read_bytes()
    result = transform(source)
    # Exclusive creation protects existing trial files too.
    with args.output.open('xb') as stream:
        stream.write(result)
    print('Experimental only; all multiplayer peers need identical cadence.')
    print('SHA256:', hashlib.sha256(result).hexdigest())


if __name__ == '__main__':
    main()
