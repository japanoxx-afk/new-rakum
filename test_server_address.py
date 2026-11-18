"""Host on the server PC (127.0.0.1) is advertised per viewer on the viewer's network."""
import unittest
from unittest import mock

import server


class Sess:
    address_for = server.ClientSession.address_for

    def __init__(self, ip):
        self.peer_ip = ip


class AddressForTests(unittest.TestCase):
    def test_remote_client_uses_observed_ip(self):
        self.assertEqual(Sess('26.1.1.1').address_for(Sess('25.2.2.2')), '26.1.1.1')

    def test_local_host_matches_viewer_network(self):
        local = ['192.168.0.5', '25.0.0.9', '26.0.0.9']
        with mock.patch.object(server.socket, 'getaddrinfo',
                               return_value=[(2, 2, 17, '', (ip, 0)) for ip in local]), \
             mock.patch.object(server.socket, 'socket', side_effect=OSError):
            host = Sess('127.0.0.1')
            self.assertEqual(host.address_for(Sess('26.7.7.7')), '26.0.0.9')
            self.assertEqual(host.address_for(Sess('25.7.7.7')), '25.0.0.9')
            self.assertEqual(host.address_for(Sess('192.168.0.20')), '192.168.0.5')
            self.assertEqual(host.address_for(Sess('127.0.0.1')), server.STATE.server_ip)
            # Server-PC player connected through its own Radmin address; Hamachi viewer
            server._own_cache = (0.0, frozenset())
            own = Sess('26.0.0.9')
            self.assertEqual(own.address_for(Sess('25.7.7.7')), '25.0.0.9')
            self.assertEqual(own.address_for(Sess('26.7.7.7')), '26.0.0.9')
            self.assertEqual(own.address_for(Sess('26.0.0.9')), '26.0.0.9')


if __name__ == '__main__':
    unittest.main()
