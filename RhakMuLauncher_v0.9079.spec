from PyInstaller.utils.hooks import collect_submodules, collect_data_files
a = Analysis(['launcher.py'], pathex=[], binaries=[],
             datas=[('server.py', '.'), ('launcher_capture.ps1', '.'), ('radmin_session.ps1', '.'),
                    ('radmin_address.ps1', '.'), ('viewport_release.json', '.'), ('minimap_release.json', '.'), ('map_preview_colors.json', '.'), ('map_preview_tiles', 'map_preview_tiles'), ('cnc_ddraw', 'cnc_ddraw'),
                    ('map_editor_web/editor', 'map_editor_web/editor'),
                    ('map_editor_web/mod/flip_ramp_tiles.tar.xz', 'map_editor_web/mod'),
                    ('game_backup/Rhakmu.exe', 'game_1000d'), ('rkp2p/TG_Net.dll', 'rkp2p')]
                   + collect_data_files('sv_ttk'),
             hiddenimports=collect_submodules('asyncio') + ['sv_ttk'], hookspath=[], hooksconfig={},
             runtime_hooks=[], excludes=[], noarchive=False, optimize=0)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='RhakMuLauncher_v0.9079',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=True,
          console=False, disable_windowed_traceback=False)
