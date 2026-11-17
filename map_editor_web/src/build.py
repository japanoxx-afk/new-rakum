"""Build the single-file map editor: src/{index.html,core.js,app.js} -> ../editor/RhakMuMapEditor.html

Run from anywhere:  python map_editor_web/src/build.py
"""
from pathlib import Path

SRC = Path(__file__).resolve().parent
OUT = SRC.parent / 'editor' / 'RhakMuMapEditor.html'

b64 = (SRC / 'sec6_default.b64').read_text().strip()
core = (SRC / 'core.js').read_text(encoding='utf-8').replace('__SEC6__', b64)
app = (SRC / 'app.js').read_text(encoding='utf-8')
html = (SRC / 'index.html').read_text(encoding='utf-8').replace('/*__CORE__*/', core).replace('/*__APP__*/', app)
OUT.write_text(html, encoding='utf-8')
print(OUT, len(html))
