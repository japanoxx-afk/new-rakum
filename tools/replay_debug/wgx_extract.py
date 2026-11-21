import sys, os, zlib
from PyInstaller.archive.readers import CArchiveReader
exe, out = sys.argv[1], sys.argv[2]
a = CArchiveReader(exe)
names = list(a.toc.keys())
print(len(names))
for n in names:
    if any(k in n.lower() for k in ("replay", "runtime", "patch", "ddraw", ".json", ".zip")) or n.endswith(".pyz"):
        print(n, a.toc[n])
for n in names:
    if n.lower().endswith((".zip", ".json", ".dll")) and ("replay" in n.lower() or "runtime" in n.lower()):
        data = a.extract(n)
        p = os.path.join(out, n.replace("/", "_").replace("\\", "_"))
        open(p, "wb").write(data); print("wrote", p, len(data))
