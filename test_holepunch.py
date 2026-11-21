import os
import tempfile
import unittest

import game_address_patch as gap
import holepunch as hp


def original():
    data = bytearray(gap.DLL_SIZE)
    data[gap.OFFSET:gap.OFFSET + 80] = gap.ORIGINAL
    return bytes(data)


PROXY = b"MZ proxy " + hp.MARK + b"TGNet_WndProc"


class HolepunchInstallTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.write("TG_Net.dll", original())

    def write(self, name, data):
        with open(os.path.join(self.d, name), "wb") as f:
            f.write(data)

    def read(self, name):
        with open(os.path.join(self.d, name), "rb") as f:
            return f.read()

    def test_install_keeps_original_and_writes_ini(self):
        self.assertEqual(hp.state(self.d), "original")
        hp.install(self.d, PROXY, True, "112.159.73.235", 30012)
        self.assertEqual(self.read("TG_Net.dll"), PROXY)
        self.assertEqual(self.read("TGNetOrg.dll"), original())
        ini = self.read("rkp2p.ini").decode()
        self.assertIn("enabled=1", ini)
        self.assertIn("server=112.159.73.235:30012", ini)
        self.assertEqual(hp.state(self.d), "proxy")

    def test_reinstall_switches_off_and_on(self):
        hp.install(self.d, PROXY, True, "1.2.3.4", 30012)
        hp.install(self.d, PROXY, False)
        self.assertIn("enabled=0", self.read("rkp2p.ini").decode())
        self.assertEqual(self.read("TGNetOrg.dll"), original())

    def test_uninstall_restores_original(self):
        hp.install(self.d, PROXY, True, "1.2.3.4", 30012)
        self.assertTrue(hp.uninstall(self.d))
        self.assertEqual(self.read("TG_Net.dll"), original())
        self.assertFalse(hp.uninstall(self.d))

    def test_refuses_unknown_dll(self):
        self.write("TG_Net.dll", b"something else")
        with self.assertRaises(ValueError):
            hp.install(self.d, PROXY, True, "1.2.3.4", 30012)
        self.assertEqual(self.read("TG_Net.dll"), b"something else")

    def test_refuses_pinned_address_dll(self):
        data = bytearray(original())
        data[gap.OFFSET:gap.OFFSET + 80] = gap.code_for("26.1.2.3")
        self.write("TG_Net.dll", bytes(data))
        with self.assertRaises(ValueError):
            hp.install(self.d, PROXY, True, "1.2.3.4", 30012)

    def test_proxy_without_original_is_refused(self):
        self.write("TG_Net.dll", PROXY)
        with self.assertRaises(ValueError):
            hp.install(self.d, PROXY, True, "1.2.3.4", 30012)

    def test_server_port(self):
        self.assertEqual(hp.server_udp_port("112.159.73.235", "112.159.73.235"), 30012)
        self.assertEqual(hp.server_udp_port("26.1.2.3", "112.159.73.235"), 47584)

    def test_server_kind(self):
        local = ("26.189.72.126", "175.202.18.56")
        self.assertEqual(hp.server_kind("112.159.73.235", local), "internet")      # NAS 인터넷 서버
        self.assertEqual(hp.server_kind("26.61.173.218", local), "vpn")            # Radmin 서버 PC
        self.assertEqual(hp.server_kind("25.10.20.30", local), "vpn")              # Hamachi
        self.assertEqual(hp.server_kind("192.168.0.5", local), "lan")
        self.assertEqual(hp.server_kind("127.0.0.1", local), "local")              # 런처 로컬 서버
        self.assertEqual(hp.server_kind("26.189.72.126", local), "local")          # 이 PC 의 Radmin 주소
        self.assertEqual(hp.server_kind("175.202.18.56", local), "local")
        self.assertEqual(hp.server_kind("", local), "unknown")


    def test_bundled_proxy_if_built(self):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rkp2p", "TG_Net.dll")
        if not os.path.isfile(path):
            self.skipTest("rkp2p 미빌드")
        with open(path, "rb") as f:
            data = f.read()
        self.assertTrue(hp.is_proxy(data))


class LauncherHolepunchSetupTests(unittest.TestCase):
    """런처 실행 단계: 인터넷 서버만 프록시, 로컬·Radmin 서버는 원래 TG_Net.dll."""

    def setUp(self):
        import launcher
        self.launcher = launcher
        self.calls = []
        self.fake = type("L", (), {})()
        self.fake.cfg = {"holepunch": True}
        self.fake._p2p_server = True
        self.fake.info_var = None
        self.orig = (hp.install, hp.uninstall, launcher.get_resource_dir, gap._local_ipv4s)
        hp.install = lambda *a, **k: self.calls.append(("install",) + a[2:])
        hp.uninstall = lambda d: self.calls.append(("uninstall",))
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "rkp2p"))
        with open(os.path.join(d, "rkp2p", "TG_Net.dll"), "wb") as f:
            f.write(PROXY)
        launcher.get_resource_dir = lambda: d
        gap._local_ipv4s = lambda: ["26.189.72.126", "175.202.18.56"]

    def tearDown(self):
        hp.install, hp.uninstall, self.launcher.get_resource_dir, gap._local_ipv4s = self.orig

    def setup(self, ip):
        self.calls.clear()
        self.launcher.App._setup_holepunch(self.fake, "G", ip, True)
        return self.calls

    def test_internet_server_uses_proxy(self):
        self.assertEqual(self.setup("112.159.73.235"), [("install", True, "112.159.73.235", 30012)])

    def test_radmin_and_local_servers_use_original_dll(self):
        for ip in ("26.61.173.218", "127.0.0.1", "26.189.72.126", "192.168.0.5", "25.1.2.3"):
            self.assertEqual(self.setup(ip), [("uninstall",)], ip)


if __name__ == "__main__":
    unittest.main()
