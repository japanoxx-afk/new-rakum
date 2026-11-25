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
            _launch_prepared_game=Mock(), _sync_rules_from_server=Mock(return_value=''))

    def setUp(self):
        # 실패해도 진짜 오류 창('게임 실행 중단')을 띄우지 않는다 (시험 실행 중 사용자 화면에 뜨던 창)
        for name in ('showerror','showinfo','showwarning'):
            p=patch.object(launcher.messagebox,name);self.addCleanup(p.stop);setattr(self,name,p.start())

    def test_multiplayer_never_touches_server_and_keeps_vpn(self):
        app=self.app();app.server.restart.return_value=(True,'ok')
        launcher.App._set_host_and_launch(app,'26.1.2.3',True)
        app._launch_prepared_game.assert_called_once_with('26.1.2.3',True)
        app._sync_rules_from_server.assert_called_once_with('26.1.2.3')
        self.showerror.assert_not_called()
        app.server.restart.assert_not_called()
        app.server.start.assert_not_called()
        app.server.stop.assert_not_called()
        app.after.assert_not_called()

    def test_single_play_button_runs_offline_menu_without_server(self):
        """싱글플레이 버튼: 서버·hosts 를 건드리지 않고 패키지(오프라인 메뉴) 실행. 실행 중에는 다시 띄우지 않는다."""
        seen=[]
        app=self.app();app.cfg={'game_dir':r'C:\game','skip_version_warning':False}
        app._prepare_game_launch=Mock(side_effect=lambda:seen.append(app._scenario_launch))
        app._start_single_game=lambda d:launcher.App._start_single_game(app,d)
        proc=Mock(poll=Mock(return_value=None))
        with patch.object(launcher.replay_memory,'find_game_pid',return_value=None), \
             patch.object(launcher.scenario_mode,'remove_maps',return_value=[]), \
             patch.object(launcher.subprocess,'Popen',side_effect=[proc,Mock(poll=Mock(return_value=None))]) as popen, \
             patch.object(launcher.HostsManager,'set_game_host') as hosts, \
             patch.object(launcher.threading,'Thread'):
            launcher.App._on_single_play(app)
            self.assertEqual(seen,[True]);self.assertFalse(app._scenario_launch)
            self.assertEqual(popen.call_count,1);self.assertIs(app._single_proc,proc)
            launcher.App._on_single_play(app)                      # 실행 중에는 다시 띄우지 않음
            self.assertEqual(popen.call_count,1)
            app.after.call_args.args[1]()                          # 아직 실행 중
            self.assertIs(app._single_proc,proc)
            proc.poll.return_value=0
            app.after.call_args.args[1]()                          # 게임이 꺼짐
            self.assertIsNone(app._single_proc);self.assertEqual(popen.call_count,1)
            launcher.App._on_single_play(app)                      # 이제 다시 실행할 수 있음
            self.assertEqual(popen.call_count,2)
            hosts.assert_not_called()
        for call in (app.server.restart,app.server.start,app.server.stop,app._launch_prepared_game):
            call.assert_not_called()
        self.showerror.assert_not_called()

    def test_local_server_launch_path_still_prepares_server(self):
        app=self.app();app.server.restart.return_value=(True,'ok')
        launcher.App._set_host_and_launch(app,'127.0.0.1',False)
        app.server.restart.assert_called_once()
        with patch.object(launcher,'is_server_running',return_value=True):
            app.after.call_args.args[1]()
        app._launch_prepared_game.assert_called_once_with('127.0.0.1',False)

    def test_failed_server_never_launches(self):
        app=self.app();app.server.restart.return_value=(False,'failed')
        launcher.App._set_host_and_launch(app,'127.0.0.1')
        app._launch_prepared_game.assert_not_called();app.after.assert_not_called()

    def test_hosts_address_matches_play_mode(self):
        for ip,multi in (('127.0.0.1',False),('26.1.2.3',True)):
            app=SimpleNamespace(cfg={'game_dir':'game'},radmin_only=Mock(get=lambda:False),_pin_game_address=Mock())
            with patch.object(launcher.os.path,'isfile',return_value=True), \
                 patch.object(launcher.HostsManager,'set_game_host') as hosts,                  patch.object(launcher.HostsManager,'read_current_ip',side_effect=['127.0.0.9',ip]), \
                 patch.object(launcher.subprocess,'Popen') as spawn:
                launcher.App._launch_prepared_game(app,ip,multi)
            hosts.assert_called_once_with(ip);spawn.assert_called_once()
            app._pin_game_address.assert_called_once_with('game',ip,multi)

    def replay_app(self):
        seen={}
        app=SimpleNamespace(cfg={'game_dir':'game'},server=Mock(),_write_game_rules=Mock(),
            _rally_override=None,_select24_override=None,_replay_play=False)
        def prepare():
            seen.update(rally=app._rally_override,sel=app._select24_override,play=app._replay_play,
                        wide=getattr(app,'_replay_wide_checks',None))
        app._prepare_game_launch=Mock(side_effect=prepare)
        return app,seen

    def test_replay_launch_uses_match_rules_and_no_server(self):
        # 게임 화면 재생은 로그인 없이 시작 저장으로 바로 들어가므로 서버·hosts 를 건드리지 않고,
        # 진행 규칙은 리플레이에 기록된 그대로 맞춘다 (예전 리플레이: 온라인 경기 = 선택 한도 12기).
        for rules,want in (({'rally_gold':False,'select_24':True,'wide_checks':True},(False,True,True)),(None,(None,False,False))):
            app,seen=self.replay_app()
            with patch.object(launcher.replay_memory,'find_game_pid',return_value=None),                  patch.object(launcher.HostsManager,'set_game_host') as hosts,                  patch.object(launcher.subprocess,'Popen') as spawn,                  patch.object(launcher.threading,'Thread') as thread:
                launcher.App._launch_replay(app,rules)
            self.assertEqual((seen['rally'],seen['sel'],seen['wide'],seen['play']),want+(True,))   # wide: 리플레이의 검사 방식
            hosts.assert_not_called();app.server.restart.assert_not_called();app.server.start.assert_not_called()
            spawn.assert_called_once()
            self.assertIn(launcher.cursor_guard.lock_game_cursor,[c.kwargs.get('target') for c in thread.call_args_list])
            self.assertEqual((app._rally_override,app._select24_override,app._replay_play,app._replay_wide_checks),(None,None,False,False))
            app._write_game_rules.assert_called_once()
            self.showerror.assert_not_called()

    def test_replay_launch_refuses_while_game_runs(self):
        app,_=self.replay_app()
        with patch.object(launcher.replay_memory,'find_game_pid',return_value=4321),              patch.object(launcher.subprocess,'Popen') as spawn:
            launcher.App._launch_replay(app,{})
        app._prepare_game_launch.assert_not_called();spawn.assert_not_called();self.showinfo.assert_called_once()

    def test_numeric_version_comparison(self):
        self.assertGreater(launcher_update.version_key('0.9024'),launcher_update.version_key('0.9020'))
        self.assertGreater(launcher_update.version_key('0.10'),launcher_update.version_key('0.9'))
        with self.assertRaises(ValueError):launcher_update.version_key('broken')

if __name__=='__main__':unittest.main()
