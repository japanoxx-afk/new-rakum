"""
RhakMu balance editing tool (STB <-> CSV <-> FDB).

Decodes the STB1 table format used in Data001.FDB and lets you edit unit/building
balance (HP, cost, build time, attack, defense, ...) via plain CSV files in Excel.

STB1 layout (little-endian):
  [0:4]   "STB1"
  [4:8]   data_off    grid start offset
  [8:12]  row_count   grid has (row_count-1) data rows
  [12:16] col_count   grid has (col_count-1) data columns
  [16:20] uint32      (key column width, unused)
  [20:..] col_count * uint16 column widths (unused)
  [..]    uint32      string-pool size (unused)
  [pool]  length-prefixed cp949 strings: first (col_count-1) are column names
  [data_off:] grid: (row_count-1)*(col_count-1) length-prefixed cp949 cells, row-major.
              Grid row 0 is a description row; real unit/building data follows.

Commands:
  python stb_tool.py extract             extract all STB files from the game FDB -> extracted_stb/
  python stb_tool.py export [NAME.STB]   STB -> CSV (default: the 5 balance tables)
  python stb_tool.py import  NAME.STB    edited CSV -> NAME.mod.STB (validates dimensions)
  python stb_tool.py apply   NAME.STB    inject NAME.mod.STB back into Data001.FDB (makes .bak)

Typical balance files:
  R1_DATA_CHAR.STB  units    (col 0 = name, 수명 = HP, 공격력좌/우 = attack, 소/마내성 = defense)
  R1_DATA_CNST.STB  buildings(col 0 = name, 수명 = HP, 건설비용 등)
  R1_DATA_SKILL.STB skills    R1_DATA_UPGL.STB upgrades   R1_DATA_DAMAGE.STB damage table
"""
import struct, sys, os, csv

ROOT     = os.path.dirname(os.path.abspath(__file__))
STB_DIR  = os.path.join(ROOT, "extracted_stb")
DATA_DIR = r"C:\Program Files (x86)\TriggerSoft\RhakMu\Data"
BALANCE  = ["R1_DATA_CHAR.STB", "R1_DATA_CNST.STB", "R1_DATA_DAMAGE.STB",
            "R1_DATA_SKILL.STB", "R1_DATA_UPGL.STB"]

# ---------- low-level ----------
def _strings(data, start, end):
    pos, out = start, []
    while pos + 2 <= end:
        n = struct.unpack_from("<H", data, pos)[0]
        if pos + 2 + n > end:
            break
        out.append(data[pos+2:pos+2+n].decode("cp949", "replace"))
        pos += 2 + n
    return out

def _enc(s):
    b = s.encode("cp949", "replace")
    return struct.pack("<H", len(b)) + b

def parse_stb(path):
    data = open(path, "rb").read()
    if data[:4] != b"STB1":
        raise ValueError("Not STB1: " + path)
    data_off  = struct.unpack_from("<I", data, 4)[0]
    n_rows = struct.unpack_from("<I", data, 8)[0] - 1
    col_count = struct.unpack_from("<I", data, 12)[0]
    n_cols = col_count - 1
    names_start = 16 + 4 + col_count * 2 + 4
    cols = _strings(data, names_start, data_off)[:n_cols]
    cells = _strings(data, data_off, len(data))
    table = [cells[r*n_cols:(r+1)*n_cols] for r in range(n_rows)]
    return cols, table

def build_stb(orig_path, csv_path, out_path):
    data = open(orig_path, "rb").read()
    data_off  = struct.unpack_from("<I", data, 4)[0]
    n_rows = struct.unpack_from("<I", data, 8)[0] - 1
    n_cols = struct.unpack_from("<I", data, 12)[0] - 1
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        body = list(csv.reader(f))[1:]
    if len(body) != n_rows:
        raise ValueError(f"CSV has {len(body)} rows, expected {n_rows}")
    grid = bytearray()
    for r in range(n_rows):
        row = (body[r] + [""] * n_cols)[:n_cols]
        for c in range(n_cols):
            grid += _enc(row[c])
    open(out_path, "wb").write(bytearray(data[:data_off]) + grid)
    return out_path, data_off + len(grid)

# ---------- FDB ----------
def _iter_idx(idx, fdb_len):
    pos = 8
    while pos < len(idx) - 8:
        fdb_off = struct.unpack_from("<I", idx, pos + 4)[0]
        ns = pos + 8
        ne = ns
        while ne < len(idx) and idx[ne] != 0:
            ne += 1
        if ne == ns:
            pos += 1; continue
        try:
            name = idx[ns:ne].decode("cp949")
        except Exception:
            pos += 1; continue
        if "\\" in name and 0 < fdb_off < fdb_len:
            yield fdb_off, name
            pos = ne + 1
        else:
            pos += 1

def extract_all():
    idx = open(os.path.join(DATA_DIR, "Data001.IDX"), "rb").read()
    fdb = open(os.path.join(DATA_DIR, "Data001.FDB"), "rb").read()
    os.makedirs(STB_DIR, exist_ok=True)
    n = 0
    for off, name in _iter_idx(idx, len(fdb)):
        if not name.upper().endswith(".STB"):
            continue
        size = struct.unpack_from("<I", fdb, off)[0]
        blob = fdb[off+4:off+4+size]
        if blob[:4] != b"STB1":
            continue
        rel = name.replace("DATA\\STB\\", "").replace("DATA/STB/", "")
        out = os.path.join(STB_DIR, rel)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        open(out, "wb").write(blob)
        n += 1
    print(f"Extracted {n} STB files -> {STB_DIR}")

def apply_to_fdb(stb_name, mod_path):
    fdb_path = os.path.join(DATA_DIR, "Data001.FDB")
    idx = open(os.path.join(DATA_DIR, "Data001.IDX"), "rb").read()
    fdb = bytearray(open(fdb_path, "rb").read())
    target = next((t for t in _iter_idx(idx, len(fdb))
                   if t[1].upper().endswith(stb_name.upper())), None)
    if not target:
        raise FileNotFoundError(stb_name + " not in IDX")
    off, name = target
    old = struct.unpack_from("<I", fdb, off)[0]
    new = open(mod_path, "rb").read()
    print(f"{name} @ {off}: old={old} new={len(new)}")
    if len(new) > old:
        raise RuntimeError(f"Modified file larger ({len(new)} > {old}); shorten values.")
    bak = fdb_path + ".bak"
    if not os.path.exists(bak):
        open(bak, "wb").write(bytes(fdb)); print("Backup ->", bak)
    struct.pack_into("<I", fdb, off, len(new))
    fdb[off+4:off+4+len(new)] = new
    open(fdb_path, "wb").write(fdb)
    print("Applied. Restart the game to see changes.")

# ---------- CLI ----------
def _resolve(name):
    if os.path.isabs(name) and os.path.exists(name):
        return name
    p = os.path.join(STB_DIR, name)
    if os.path.exists(p):
        return p
    for root, _, files in os.walk(STB_DIR):
        for f in files:
            if f.upper() == name.upper():
                return os.path.join(root, f)
    raise FileNotFoundError(name)

def export(name):
    p = _resolve(name)
    cols, table = parse_stb(p)
    out = p[:-4] + ".csv"
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f); w.writerow(cols); w.writerows(table)
    print(f"{os.path.basename(p)}: {len(table)} rows x {len(cols)} cols -> {out}")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "extract":
        extract_all()
    elif cmd == "export":
        for n in (sys.argv[2:] or BALANCE):
            export(n)
    elif cmd == "import":
        p = _resolve(sys.argv[2])
        out, size = build_stb(p, p[:-4] + ".csv", p[:-4] + ".mod.STB")
        print(f"Built {out} ({size} bytes)")
    elif cmd == "apply":
        p = _resolve(sys.argv[2])
        apply_to_fdb(os.path.basename(p), p[:-4] + ".mod.STB")
    else:
        print(__doc__)
