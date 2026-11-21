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

    def test_bundled_proxy_if_built(self):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rkp2p", "TG_Net.dll")
        if not os.path.isfile(path):
            self.skipTest("rkp2p 미빌드")
        with open(path, "rb") as f:
            data = f.read()
        self.assertTrue(hp.is_proxy(data))


if __name__ == "__main__":
    unittest.main()
