"""종족 이름 한글 그림 만들기 -> race_name_patch.py 의 SPRITES 값.

게임 방 화면의 종족 이름(Mu hŭl / Aren / Marduke)은 글자가 아니라 그림이다 (Data002.FDB 의
DATA\\MENUDATA\\MENUCOMMON.S16 31~36번: 이름마다 보통(흰색)·고른 것(주황) 두 장).
이 도구는 같은 색으로 한글 이름 그림을 만들어 파이썬 상수로 찍는다. 게임 그림은 쓰지 않는다.

    python tools/make_race_name_sprites.py [글꼴.ttc] [글꼴 번호]

Pillow 와 한글 글꼴이 필요하다 (기본: Noto Sans CJK KR Bold 13px — 만든 PC 의 글꼴 경로).
"""
import base64
import struct
import sys
import zlib

from PIL import Image, ImageDraw, ImageFont

NAMES = ("위국군", "아스트리아", "바르바로이")
# 원본 그림에서 읽은 색: 글자 색, 가장자리(배경에 섞인) 색
STYLES = (((255, 250, 255), (90, 48, 41)), ((230, 153, 16), (90, 40, 24)))
SIZE = 13                   # 14px 은 원본 그림 여섯 장이 차지하던 자리(구역마다 6836바이트)를 넘는다
THRESHOLD = 0.22            # 이보다 옅은 가장자리는 버린다 (그림에 투명도가 없어 배경색과 미리 섞어 둔다)


def to565(rgb):
    r, g, b = rgb
    return max(1, (r * 31 // 255) << 11 | (g * 63 // 255) << 5 | (b * 31 // 255))   # 0 은 '빈 칸' 표시로 쓴다


def render(text, font, fill, edge):
    canvas = Image.new("L", (240, 48), 0)
    ImageDraw.Draw(canvas).text((4, 4), text, font=font, fill=255)
    cover = canvas.crop(canvas.getbbox())
    w, h = cover.size
    px = cover.load()
    out = []
    for y in range(h):
        for x in range(w):
            c = px[x, y] / 255
            out.append(to565(tuple(round(e + (f - e) * c) for e, f in zip(edge, fill))) if c >= THRESHOLD else 0)
    return w, h, out


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
    index = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    font = ImageFont.truetype(path, SIZE, index=index)
    print("# tools/make_race_name_sprites.py 가 만든 값 (%s %s %dpx). 고치려면 그 도구를 다시 돌린다." % (*font.getname(), SIZE))
    print("SPRITES = (")
    for name in NAMES:
        for fill, edge in STYLES:
            w, h, pixels = render(name, font, fill, edge)
            blob = base64.b64encode(zlib.compress(struct.pack(f"<{w * h}H", *pixels), 9)).decode()
            print(f'    ({w}, {h}, "{blob}"),')
    print(")")


if __name__ == "__main__":
    main()
