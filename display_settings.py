"""Conservative cnc-ddraw output settings; does not change engine resolution."""
import hashlib
import os
from pathlib import Path
import tempfile

RENDERERS = ('auto', 'direct3d9', 'opengl', 'gdi')
FILTERS = {'Nearest neighbor': 0, 'Bilinear': 1, 'Bicubic': 2, 'Lanczos': 3}


def read_section(text, section='ddraw'):
    values, active = {}, False
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('[') and line.endswith(']'):
            active = line[1:-1].casefold() == section.casefold()
        elif active and '=' in line and not line.startswith((';', '#')):
            key, value = line.split('=', 1)
            values[key.strip().casefold()] = value.strip()
    return values


def update_section(text, values, section='ddraw'):
    """Change only this section, insert missing keys, preserve other profiles."""
    newline = '\r\n' if '\r\n' in text else '\n'
    lines = text.splitlines(keepends=True)
    remaining = dict(values)
    result, active, found = [], False, False

    def flush():
        if remaining:
            if result and not result[-1].endswith(('\n', '\r')):
                result[-1] += newline
            result.extend(f'{key}={value}{newline}' for key, value in remaining.items())
            remaining.clear()

    for line in lines:
        clean = line.strip()
        if clean.startswith('[') and clean.endswith(']'):
            if active:
                flush()
            active = clean[1:-1].casefold() == section.casefold()
            if active and found:
                raise ValueError(f'중복 [{section}] 섹션: 안전하게 수동 확인이 필요합니다.')
            found |= active
        if active and '=' in clean and not clean.startswith((';', '#')):
            key = clean.split('=', 1)[0].strip().casefold()
            if key in values:
                # Collapse duplicate keys in the edited section.
                if key in remaining:
                    result.append(f'{key}={remaining.pop(key)}{newline}')
                continue
        result.append(line)
    if active:
        flush()
    elif not found:
        if result and not result[-1].endswith(('\n', '\r')):
            result[-1] += newline
        result.append(f'[{section}]{newline}')
        flush()
    return ''.join(result)


class WindowModeManager:
    def __init__(self, game_dir):
        self.game_dir = game_dir

    @property
    def ini_path(self):
        return os.path.join(self.game_dir, 'ddraw.ini')

    @property
    def available(self):
        return Path(self.ini_path).is_file()

    def read_settings(self):
        result = dict(windowed=False, width=0, height=0, shader='Bicubic',
                      maintas=True, renderer='auto', confine=True)
        if not self.available:
            return result
        values = read_section(Path(self.ini_path).read_bytes().decode('utf-8-sig'))
        for key in ('width', 'height'):
            try:
                result[key] = max(0, int(values.get(key, 0)))
            except ValueError:
                pass
        for key in ('windowed', 'maintas'):
            if key in values:
                result[key] = values[key].lower() == 'true'
        result['confine'] = values.get('devmode', 'false').lower() != 'true'
        result['renderer'] = values.get('renderer', 'auto')
        result['shader'] = values.get('shader', 'Bicubic')
        if result['renderer'].startswith('direct3d9'):
            reverse = {str(v): k for k, v in FILTERS.items()}
            result['shader'] = reverse.get(values.get('d3d9_filter', '2'), 'Bicubic')
        return result

    def apply_settings(self, windowed, width, height, shader='', maintas=True,
                       renderer='auto', confine=True):
        try:
            if (width, height) != (0, 0) and not (320 <= width <= 7680 and 200 <= height <= 4320):
                raise ValueError('출력 크기는 320×200~7680×4320 또는 원본(0x0)이어야 합니다.')
            if renderer not in RENDERERS:
                raise ValueError('지원하지 않는 렌더러입니다.')
            if shader not in FILTERS:
                raise ValueError('지원 필터: Nearest neighbor, Bilinear, Bicubic, Lanczos')
            path = Path(self.ini_path)
            original = path.read_bytes()
            text = original.decode('utf-8-sig')
            if not (Path(self.game_dir) / 'ddraw.dll').is_file():
                raise ValueError('ddraw.dll이 없습니다. 출력 설정을 적용하지 않았습니다.')
            # A per-game override can silently win over the global section.
            # Explicitly refuse rather than editing another profile or claiming success.
            override = read_section(text, 'rhakmu')
            edited_keys = {'width', 'height', 'windowed', 'fullscreen', 'maintas',
                           'shader', 'renderer', 'devmode', 'd3d9_filter', 'aspect_ratio'}
            if edited_keys.intersection(override):
                raise ValueError('[rhakmu] 개별 출력 설정이 있습니다. 충돌 방지를 위해 적용을 중단합니다.')
            values = dict(width=width, height=height, windowed=str(bool(windowed)).lower(),
                          fullscreen=str(not windowed).lower(), maintas=str(bool(maintas)).lower(),
                          aspect_ratio='', renderer=renderer, shader=shader,
                          d3d9_filter=FILTERS[shader], devmode=str(not confine).lower(), adjmouse='true')
            changed = update_section(text, values).encode('utf-8')
            backup = path.with_name('ddraw.ini.bak_' + hashlib.sha256(original).hexdigest()[:16])
            if backup.exists() and backup.read_bytes() != original:
                raise ValueError('백업 내용이 예상과 다릅니다. 적용을 중단합니다.')
            if not backup.exists():
                with backup.open('xb') as stream:
                    stream.write(original)
            fd, temp = tempfile.mkstemp(prefix='.ddraw-', suffix='.tmp', dir=path.parent)
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(changed)
                    stream.flush()
                    os.fsync(stream.fileno())
                if path.read_bytes() != original:
                    raise ValueError('설정 파일이 다른 프로그램에서 변경되었습니다. 다시 시도하세요.')
                os.replace(temp, path)
            finally:
                if os.path.exists(temp):
                    os.unlink(temp)
            return True, ('출력 설정을 저장했습니다. 내부 지도 해상도는 바뀌지 않습니다.\n'
                          f'백업: {backup.name}\n원복: 게임 종료 후 백업을 ddraw.ini로 복사하세요.')
        except (OSError, UnicodeError, ValueError) as exc:
            return False, str(exc)
