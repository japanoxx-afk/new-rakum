import minimap_patch
SEQ = bytes.fromhex("830dc812b40001b998569100b8e0914900ffd0")
def prepare(path, *a):
    minimap_patch.prepare(path, *a)
    b = bytearray(open(path, "rb").read())
    i = b.find(SEQ); assert i > 0 and b.find(SEQ, i + 1) < 0, i
    b[i:i + len(SEQ)] = b"\x90" * len(SEQ)
    open(path, "wb").write(b)
    print("reveal removed at file offset", hex(i), flush=True)
