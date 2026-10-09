from PyInstaller.utils.hooks import collect_submodules
a = Analysis(['launcher.py'], pathex=[], binaries=[],
             datas=[('server.py', '.'), ('launcher_capture.ps1', '.'), ('radmin_session.ps1', '.'),
                    ('radmin_address.ps1', '.'), ('viewport_release.json', '.')],
             hiddenimports=collect_submodules('asyncio'), hookspath=[], hooksconfig={},
             runtime_hooks=[], excludes=[], noarchive=False, optimize=0)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='RhakMuLauncher_v0.9024',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=True,
          console=False, disable_windowed_traceback=False)
