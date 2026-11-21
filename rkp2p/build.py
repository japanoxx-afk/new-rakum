"""Build rkp2p (hole-punching TG_Net.dll proxy) and its test files with zig (pip install ziglang).

    python rkp2p/build.py

Outputs rkp2p/TG_Net.dll (bundled into the launcher) and rkp2p/test/{TG_Net.dll,TGNetOrg.dll,harness.exe,realharness.exe}.
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TEST = os.path.join(HERE, "test")
CC = [sys.executable, "-m", "ziglang", "cc", "-target", "x86-windows-gnu", "-O2", "-s"]


def cc(*args):
    print(" ".join(args))
    subprocess.run(CC + list(args), check=True, cwd=HERE)


def main():
    cc("-shared", "-o", "TG_Net.dll", "rkp2p.c", "tg_net.def", "-lws2_32")
    cc("-shared", "-o", os.path.join("test", "TGNetOrg.dll"), os.path.join("test", "fake_tgnet.c"), "-lwsock32")
    cc("-o", os.path.join("test", "harness.exe"), os.path.join("test", "harness.c"))
    cc("-o", os.path.join("test", "realharness.exe"), os.path.join("test", "realharness.c"), "-lws2_32", "-luser32")
    shutil.copy(os.path.join(HERE, "TG_Net.dll"), os.path.join(TEST, "TG_Net.dll"))
    for d in (HERE, TEST):          # zig leaves import libraries / pdb next to the outputs
        for f in os.listdir(d):
            if f.endswith((".lib", ".pdb", ".a")):
                os.remove(os.path.join(d, f))


if __name__ == "__main__":
    main()
