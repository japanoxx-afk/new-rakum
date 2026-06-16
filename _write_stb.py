"""
Write a modified CSV back into an STB1 file, then repack it into the FDB archive.

Strategy: edit values IN-PLACE in the value grid. The grid cells are length-prefixed
cp949 strings; we re-encode only the grid (header + string pool / column names are
preserved byte-for-byte). data_off, row_count, col_count are unchanged. The grid size
can change (different number of digits), so the resulting STB may differ in length -
that is fine because the FDB stores an explicit [uint32 size] before each file.

Usage:
  python _write_stb.py build  <name.STB> <name.csv> -> writes modified STB next to original (.mod.STB)
  python _write_stb.py repack <name.STB>            -> injects modified STB back into Data001.FDB
"""
import struct, sys, os, csv

STB_DIR  = r"C:\Users\seo\Documents\라크무-claude\extracted_stb"
DATA_DIR = r"C:\Program Files (x86)\TriggerSoft\RhakMu\Data"

def _enc_cell(s):
    b = s.encode("cp949", errors="replace")
    return struct.pack("<H", len(b)) + b

def build_stb(orig_path, csv_path, out_path):
    data = open(orig_path, "rb").read()
    if data[:4] != b"STB1":
        raise ValueError("Not STB1")
    data_off  = struct.unpack_from("<I", data, 4)[0]
    row_count = struct.unpack_from("<I", data, 8)[0]
    col_count = struct.unpack_from("<I", data, 12)[0]
    n_cols = col_count - 1
    n_rows = row_count - 1

    # Read CSV (skip header row of column names)
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    body = rows[1:]  # drop column-name header
    if len(body) != n_rows:
        raise ValueError(f"CSV has {len(body)} data rows, expected {n_rows}")

    # Rebuild grid bytes
    grid = bytearray()
    for r in range(n_rows):
        row = body[r]
        if len(row) < n_cols:
            row = row + [""] * (n_cols - len(row))
        for c in range(n_cols):
            grid += _enc_cell(row[c])

    # Header + string pool (everything before data_off) preserved verbatim
    new = bytearray(data[:data_off]) + grid
    open(out_path, "wb").write(new)
    print(f"Built {out_path}  ({len(new)} bytes, grid {len(grid)} bytes)")
    return out_path

def repack_fdb(stb_name, mod_stb_path):
    """Replace stb_name's data inside Data001.FDB with the modified STB bytes."""
    idx_path = os.path.join(DATA_DIR, "Data001.IDX")
    fdb_path = os.path.join(DATA_DIR, "Data001.FDB")
    idx = open(idx_path, "rb").read()
    fdb = bytearray(open(fdb_path, "rb").read())

    # Locate the IDX entry whose name ends with stb_name -> its fdb offset
    target = None
    pos = 8
    while pos < len(idx) - 8:
        fdb_off = struct.unpack_from("<I", idx, pos + 4)[0]
        name_start = pos + 8
        name_end = name_start
        while name_end < len(idx) and idx[name_end] != 0:
            name_end += 1
        if name_end == name_start:
            pos += 1; continue
        try:
            name = idx[name_start:name_end].decode("cp949")
        except Exception:
            pos += 1; continue
        if "\\" in name and 0 < fdb_off < len(fdb):
            if name.upper().endswith(stb_name.upper()):
                target = (fdb_off, name)
                break
            pos = name_end + 1
        else:
            pos += 1
    if not target:
        raise FileNotFoundError(f"{stb_name} not found in IDX")
    fdb_off, name = target

    old_size = struct.unpack_from("<I", fdb, fdb_off)[0]
    new_data = open(mod_stb_path, "rb").read()
    new_size = len(new_data)
    print(f"Found {name} @ FDB {fdb_off}: old_size={old_size}, new_size={new_size}")

    if new_size <= old_size:
        # Fits in place: overwrite size + data, zero-pad the slack (kept inside record)
        struct.pack_into("<I", fdb, fdb_off, new_size)
        fdb[fdb_off+4:fdb_off+4+new_size] = new_data
        # leave trailing old bytes as-is (size field now smaller, so they're ignored)
        backup = fdb_path + ".bak"
        if not os.path.exists(backup):
            open(backup, "wb").write(open(fdb_path, "rb").read())
            print(f"Backup -> {backup}")
        open(fdb_path, "wb").write(fdb)
        print(f"Repacked in-place. FDB written ({len(fdb)} bytes).")
    else:
        raise RuntimeError(
            f"New STB ({new_size}) larger than original slot ({old_size}). "
            f"In-place repack unsafe. Reduce value lengths or implement append+IDX-rewrite."
        )

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "build":
        stb = sys.argv[2]
        csvf = sys.argv[3]
        stb_path = stb if os.path.isabs(stb) else os.path.join(STB_DIR, stb)
        csv_path = csvf if os.path.isabs(csvf) else os.path.join(STB_DIR, csvf)
        out = stb_path.replace(".STB", ".mod.STB")
        build_stb(stb_path, csv_path, out)
    elif mode == "repack":
        stb = sys.argv[2]
        stb_path = stb if os.path.isabs(stb) else os.path.join(STB_DIR, stb)
        mod = stb_path.replace(".STB", ".mod.STB")
        repack_fdb(os.path.basename(stb), mod)
    else:
        print(__doc__)
