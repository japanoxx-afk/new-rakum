"""
Extract STB files from RhakMu Data001.FDB using Data001.IDX.
IDX entry format: [uint32 unknown][uint32 fdb_offset][name\0]
FDB file format:  [uint32 file_size][file_data...]
"""
import struct, os, sys

DATA_DIR = r"C:\Program Files (x86)\TriggerSoft\RhakMu\Data"
OUT_DIR  = r"C:\Users\seo\Documents\라크무-claude\extracted_stb"

idx_path = os.path.join(DATA_DIR, "Data001.IDX")
fdb_path = os.path.join(DATA_DIR, "Data001.FDB")

idx = open(idx_path, "rb").read()
fdb = open(fdb_path, "rb").read()

# Find all null-terminated names and the uint32 just before each name
# Strategy: scan for sequences where we have [0x00][uint32][printable_or_korean_chars..][0x00]
entries = []
pos = 8
while pos < len(idx) - 8:
    # Try to read uint32 at pos (unknown) and uint32 at pos+4 (fdb_offset), then name at pos+8
    if pos + 8 >= len(idx):
        break
    unk = struct.unpack_from("<I", idx, pos)[0]
    fdb_off = struct.unpack_from("<I", idx, pos + 4)[0]
    name_start = pos + 8
    # Read null-terminated name
    name_end = name_start
    while name_end < len(idx) and idx[name_end] != 0:
        name_end += 1
    if name_end == name_start:
        pos += 1
        continue
    try:
        name = idx[name_start:name_end].decode("cp949")
    except Exception:
        pos += 1
        continue
    # Validate: fdb_offset should be within FDB, name should look like a path
    if '\\' in name and fdb_off < len(fdb) and fdb_off > 0:
        entries.append((fdb_off, name))
        pos = name_end + 1
    else:
        pos += 1

print(f"Found {len(entries)} entries")

# Extract only STB files
os.makedirs(OUT_DIR, exist_ok=True)
extracted = 0
for fdb_off, name in entries:
    if not name.upper().endswith(".STB"):
        continue
    # FDB: first 4 bytes = file size, then file data
    if fdb_off + 4 > len(fdb):
        print(f"  SKIP (out of range): {name}")
        continue
    file_size = struct.unpack_from("<I", fdb, fdb_off)[0]
    data_start = fdb_off + 4
    if data_start + file_size > len(fdb):
        print(f"  SKIP (size overflow): {name} size={file_size}")
        continue
    file_data = fdb[data_start:data_start + file_size]
    # Verify STB1 magic
    if file_data[:4] != b"STB1":
        print(f"  SKIP (bad magic {file_data[:4]}): {name}")
        continue
    # Save preserving subdirectory structure
    rel = name.replace("DATA\\STB\\", "").replace("DATA/STB/", "")
    out_path = os.path.join(OUT_DIR, rel)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    open(out_path, "wb").write(file_data)
    rows = struct.unpack_from("<I", file_data, 4)[0]
    cols = struct.unpack_from("<I", file_data, 8)[0]
    print(f"  OK: {rel}  ({rows} rows x {cols} cols, {file_size} bytes)")
    extracted += 1

print(f"\nExtracted {extracted} STB files to {OUT_DIR}")
