"""
Parse RhakMu STB1 files and export to CSV (and back).

STB1 layout (little-endian), fully reverse-engineered:
  [0..3]   "STB1"
  [4..7]   data_off   - byte offset where the value grid begins
  [8..11]  row_count  - grid is (row_count-1) data rows (row 0 of header meta excluded)
  [12..15] col_count  - grid is (col_count-1) data columns
  [16..19] uint32     - key-column width / misc (unused)
  [20..]   col widths : col_count * uint16 (display pixels, unused)
  [..]     uint32     - string-pool size (unused for parsing)
  [pool]   length-prefixed cp949 strings: first (col_count-1) are column names,
           the rest are row-key labels (a parallel name list, not needed for the grid)
  [data_off..] value grid: (row_count-1)*(col_count-1) length-prefixed cp949 cells,
           row-major. Grid row 0 is a description/header row; building/unit data follows.
"""
import struct, sys, os, csv

STB_DIR = r"C:\Users\seo\Documents\라크무-claude\extracted_stb"

def _parse_strings(data, start, end):
    """Parse consecutive [uint16 len][cp949 bytes] strings in [start, end)."""
    pos = start
    out = []
    while pos + 2 <= end:
        slen = struct.unpack_from("<H", data, pos)[0]
        if pos + 2 + slen > end:
            break
        out.append(data[pos+2:pos+2+slen].decode("cp949", errors="replace"))
        pos += 2 + slen
    return out, pos

def parse_stb(path):
    data = open(path, "rb").read()
    if data[:4] != b"STB1":
        raise ValueError("Not STB1")
    data_off  = struct.unpack_from("<I", data, 4)[0]
    row_count = struct.unpack_from("<I", data, 8)[0]
    col_count = struct.unpack_from("<I", data, 12)[0]

    n_cols = col_count - 1          # real data columns
    n_rows = row_count - 1          # real data rows (incl. grid row 0 = description)

    # Column names: string pool begins after header(16) + uint32(4) + widths(col_count*2) + uint32(4)
    names_start = 16 + 4 + col_count * 2 + 4
    pool, _ = _parse_strings(data, names_start, data_off)
    col_names = pool[:n_cols] if len(pool) >= n_cols else pool

    # Value grid
    cells, _ = _parse_strings(data, data_off, len(data))
    table = [cells[r*n_cols:(r+1)*n_cols] for r in range(n_rows)]

    return col_names, table

def find_stb(name):
    path = os.path.join(STB_DIR, name)
    if os.path.exists(path):
        return path
    for root, dirs, files in os.walk(STB_DIR):
        for f in files:
            if f.upper() == name.upper() or f.upper() == name.upper().replace(".STB","") + ".STB":
                return os.path.join(root, f)
    raise FileNotFoundError(name)

def show(name, max_rows=40, max_cols=10):
    path = find_stb(name)
    cols, table = parse_stb(path)
    print(f"\n=== {os.path.basename(path)} ({len(table)} rows x {len(cols)} cols) ===")
    print("IDX | " + " | ".join(f"{h[:16]:16}" for h in cols[:max_cols]))
    print("-"*120)
    for i, row in enumerate(table[:max_rows]):
        print(f"{i:3d} | " + " | ".join(f"{str(v)[:16]:16}" for v in row[:max_cols]))
    if len(table) > max_rows:
        print(f"  ... ({len(table)-max_rows} more rows)")

def to_csv(name, out_path=None):
    path = find_stb(name)
    cols, table = parse_stb(path)
    if not out_path:
        out_path = path.replace(".STB", ".csv")
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(table)
    print(f"Saved {len(table)} rows x {len(cols)} cols -> {out_path}")
    return out_path

if __name__ == "__main__":
    if len(sys.argv) < 2:
        for name in ["R1_DATA_CHAR.STB", "R1_DATA_CNST.STB", "R1_DATA_DAMAGE.STB",
                     "R1_DATA_SKILL.STB", "R1_DATA_UPGL.STB"]:
            try:
                to_csv(name)
            except Exception as e:
                print(f"{name}: {e}")
    else:
        for name in sys.argv[1:]:
            try:
                show(name)
                to_csv(name)
            except Exception as e:
                print(f"Error: {e}")
