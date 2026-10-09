"""Explicit, reversible trial installer. Not part of the official updater."""
import hashlib
import os
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import command_cadence_trial as trial
import viewport_patch

DEFAULT = r'C:\Program Files (x86)\TriggerSoft\RhakMu\Rhakmu.exe'


def apply(path, enabled):
    path = Path(path).resolve(strict=True)
    if path.name.lower() != 'rhakmu.exe':
        raise ValueError('Rhakmu.exe를 선택하세요.')
    viewport_patch.ensure_closed()
    original = path.read_bytes()
    changed = trial.transform(original, enabled)
    if changed == original:
        return '이미 요청한 상태입니다.'
    # Backup each exact input before replacing; restoration normalizes only
    # the cadence byte, preserving later independent configuration changes.
    backup = path.with_name(path.name + '.bak_cadence_' + hashlib.sha256(original).hexdigest()[:16])
    if backup.exists():
        if backup.read_bytes() != original:
            raise ValueError('백업 충돌: 파일을 교체하지 않았습니다.')
    else:
        with backup.open('xb') as stream:
            stream.write(original)
            stream.flush()
            os.fsync(stream.fileno())
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='cadence-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(changed)
            stream.flush()
            os.fsync(stream.fileno())
        if path.read_bytes() != original:
            raise ValueError('게임 파일이 다른 프로그램에 의해 변경됐습니다.')
        viewport_patch.ensure_closed()
        os.replace(temporary, path)
        temporary = None
        if path.read_bytes() != changed:
            raise ValueError('교체 후 검증 실패. 백업을 보존했습니다.')
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return ('99ms 시험 패치 적용 완료' if enabled else '기존 165ms 전송 간격 복원 완료') + '\n백업: ' + str(backup)


def main():
    root = tk.Tk()
    root.title('라크무 4턴 유지 · 99ms 통신 시험 패치')
    root.geometry('680x310')
    root.minsize(680, 310)
    frame = ttk.Frame(root, padding=16)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='시험용입니다. 정식 배포 / 멀티 안정성 검증 전입니다.', foreground='#a00000').pack(anchor='w')
    ttk.Label(frame, text='양쪽 모두 같은 패치를 사용하세요. 구버전과 혼용하지 마세요.\n4턴과 프레임 타이머 유지 · 전송 간격만 165 → 약 99ms\n게임과 기존 Launcher.exe를 종료하고 적용하세요.\n정식 런처의 실행 버튼은 시험 패치를 차단할 수 있습니다.\n적용 후 설치 폴더의 기존 Launcher.exe로 실행하세요.', justify='left').pack(anchor='w', pady=10)
    path = tk.StringVar(value=DEFAULT)
    ttk.Entry(frame, textvariable=path).pack(fill='x')
    def browse():
        selected = filedialog.askopenfilename(title='설치된 Rhakmu.exe 선택', filetypes=[('게임', 'Rhakmu.exe')])
        if selected:
            path.set(selected)
    ttk.Button(frame, text='게임 파일 선택', command=browse).pack(anchor='w', pady=6)
    def change(enabled):
        if enabled and not messagebox.askyesno('멀티 시험 패치', '상대방도 동일 패치가 필요합니다.\n네트워크 지연 변동이 크면 게임이 느려질 수 있습니다.\n시험 패치를 적용할까요?'):
            return
        try:
            messagebox.showinfo('완료', apply(path.get(), enabled))
        except Exception as error:
            messagebox.showerror('적용 중단', str(error))
    buttons = ttk.Frame(frame)
    buttons.pack(fill='x', pady=8)
    ttk.Button(buttons, text='99ms 시험 패치 적용', command=lambda: change(True)).pack(side='left')
    ttk.Button(buttons, text='기존 전송 간격으로 원복', command=lambda: change(False)).pack(side='left', padx=12)
    root.mainloop()


if __name__ == '__main__':
    main()
