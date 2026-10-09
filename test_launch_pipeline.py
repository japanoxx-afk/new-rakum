import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace
import launcher
import launcher_update

class PipelineTests(unittest.TestCase):
    def test_protocol_probe_requires_exact_response(self):
        import struct
        for reply,expected in ((struct.pack('<HHI',0x01ff,8,0),True),(b'HTTP/1.1',False),(b'',False)):
            connection=Mock()
            connection.recv.return_value=reply
            context=Mock()
            context.__enter__=Mock(return_value=connection)
            context.__exit__=Mock(return_value=False)
            with patch.object(launcher.socket,'create_connection',return_value=context):
                self.assertEqual(launcher.verify_local_rhakmu_server(),expected)
            connection.sendall.assert_called_once_with(struct.pack('<HH4sI',0x01ff,12,b'RHAK',1000))

    def test_server_start_button_restarts_instead_of_rejecting(self):
        app=SimpleNamespace(server=Mock(),_update_status=Mock())
        app.server.restart.return_value=(True,'ok')
        launcher.App._on_start(app)
        app.server.restart.assert_called_once()
        app.server.start.assert_not_called()

    def app(self):
        return SimpleNamespace(_prepare_game_launch=Mock(), server=Mock(),
            radmin_only=Mock(get=lambda:False), info_var=Mock(), after=Mock(),
            _launch_prepared_game=Mock())

    def test_multiplayer_never_touches_server_and_keeps_vpn(self):
        app=self.app();app.server.restart.return_value=(True,'ok')
        launcher.App._set_host_and_launch(app,'26.1.2.3',True)
        app._launch_prepared_game.assert_called_once_with('26.1.2.3',True)
        app.server.restart.assert_not_called()
        app.server.start.assert_not_called()
        app.server.stop.assert_not_called()
        app.after.assert_not_called()

    def test_singleplayer_still_prepares_local_server(self):
        app=self.app();app.server.restart.return_value=(True,'ok')
        launcher.App._set_host_and_launch(app,'127.0.0.1',False)
        app.server.restart.assert_called_once()
        with patch.object(launcher,'is_server_running',return_value=True):
            app.after.call_args.args[1]()
        app._launch_prepared_game.assert_called_once_with('127.0.0.1',False)

    def test_failed_server_never_launches(self):
        app=self.app();app.server.restart.return_value=(False,'failed')
        with patch.object(launcher.messagebox,'showerror'):
            launcher.App._set_host_and_launch(app,'127.0.0.1')
        app._launch_prepared_game.assert_not_called();app.after.assert_not_called()

    def test_hosts_address_matches_play_mode(self):
        for ip,multi in (('127.0.0.1',False),('26.1.2.3',True)):
            app=SimpleNamespace(cfg={'game_dir':'game'},radmin_only=Mock(get=lambda:False))
            with patch.object(launcher.os.path,'isfile',return_value=True), \
                 patch.object(launcher.HostsManager,'set_game_host') as hosts, \
                 patch.object(launcher.subprocess,'Popen') as spawn:
                launcher.App._launch_prepared_game(app,ip,multi)
            hosts.assert_called_once_with(ip);spawn.assert_called_once()

    def test_numeric_version_comparison(self):
        self.assertGreater(launcher_update.version_key('0.9024'),launcher_update.version_key('0.9020'))
        self.assertGreater(launcher_update.version_key('0.10'),launcher_update.version_key('0.9'))
        with self.assertRaises(ValueError):launcher_update.version_key('broken')

if __name__=='__main__':unittest.main()
