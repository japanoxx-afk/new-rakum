"""Prepare already-copied isolated games; never edits the installed game."""
from pathlib import Path
import minimap_preview_patch
import viewport_patch
import minimap_preview_v5

ROOT = Path(__file__).parent / 'research/runtime/minimap-preview-v5-20261011'
if __name__ == '__main__':
    for name, highres in [('highres', True), ('original', False)]:
        folder = ROOT / name
        source = folder / 'Rhakmu.before-minimap.exe'
        data = viewport_patch.transform(source.read_bytes(), highres)
        baseline = data
        data = minimap_preview_v5.build(data)
        with (folder / 'Rhakmu.exe').open('xb') as stream:
            stream.write(data)
        assert minimap_preview_v5.restore(data) == baseline
        print(name, 'verified', len(data))
