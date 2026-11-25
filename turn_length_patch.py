"""멀티플레이 명령 전송 간격 (턴 길이) 줄이기 (Rhakmu.exe 1.000d).

분석 (Game_Multi 0x4D7A80, 턴 처리 0x44A840):
  매 프레임 시뮬레이션을 돌리고, 프레임 [0xB412B4] 이 5 의 배수일 때만(0x4D7B96 mov ecx,5) 그동안 모인 내 명령을
  한 턴으로 묶어 보낸다(0x447AF0). 그 턴은 '명령 지연 턴'([net+0x48], 기본 4) 뒤의 턴 경계에서 모든 PC가 함께 실행한다.
  프레임은 33ms 이므로 한 턴 = 165ms, 클릭부터 실행까지 = 다음 경계까지 기다림(평균 반 턴) + (지연 턴 - 1) 턴
  -> 4턴이면 약 0.58초 (실측 0.53~0.63초와 일치). 지연 턴 수를 그대로 두고 턴 길이를 줄여도 같은 비율로 빨라진다:
      5프레임(원래): 약 0.58초   3프레임: 약 0.35초   2프레임: 약 0.23초   (모두 지연 4턴 기준)
  대신 네트워크가 견디는 여유(상대 턴이 늦게 와도 멈추지 않는 시간)도 같은 비율로 줄어든다 (3턴 x 턴 길이).

  속도 조절(0x44A950~): 상대 턴이 아직 안 왔으면 기다리고(0x44A410) 프레임 시간 [0xB412B8] 을 +2ms (66ms 까지),
  모두 왔고 '가장 적게 쌓인 플레이어의 대기 턴 수'가 3 이상일 때만 -1ms (33ms 까지) 되돌린다 (0x44A98B cmp edx,3).
  받은 패킷은 턴 경계에서만 읽으므로 상대 턴은 보통 1턴, 어긋나면 2턴 늦게 보인다. 턴이 짧아지면 2턴 늦는 일이 잦아
  대기 턴 수가 2 에 머물고, 그러면 한 번 느려진 속도가 되돌아오지 않는다 — 예전 99ms 실험(v0.9028~v0.9031)의
  '멀티 속도 저하' 로 보인다. 그래서 턴을 줄일 때는 되돌리는 기준도 2 로 낮춘다 (2턴 여유 = 5프레임 때 1턴보다 길다).
  프레임 시간은 PC마다 따로 가는 값이라 진행(동기)에는 영향이 없다. 기다림·끊김 판정(1.75초, 40초)은 실제 시간 기준이라 그대로.

패치: 0x4D7B97 (턴 길이 프레임 수) = 5 | 3 | 2, 0x44A98D (속도 되돌림 기준) = 3 (원래) | 2 (턴을 줄였을 때).
턴 길이는 시뮬레이션 규칙이다 — 같이 하는 모든 PC가 같아야 한다 (다르면 느려지다 무승부). 런처가 서버 PC 규칙(/rules)과
리플레이 규칙(turn_frames)으로 맞춘다. 리플레이 재생은 replay_record_patch 가 같은 턴 길이로 rand 를 뽑는다.
"""
FRAMES_SITE = 0xD7B97                 # 0x4D7B96: b9 [05] 00 00 00   mov ecx, 5
RECOVER_SITE = 0x4A98D                # 0x44A98B: 83 fa [03]         cmp edx, 3
CONTEXT = ((0xD7B96, bytes.fromhex("b9"), 0xD7B98, bytes.fromhex("000000f7f1")),
           (0x4A98B, bytes.fromhex("83fa"), 0x4A98E, bytes.fromhex("7c16")))
ORIGINAL = 5
CHOICES = (5, 3, 2)


def _recover(frames: int) -> int:
    return 3 if frames == ORIGINAL else 2


def state(data) -> int:
    """지금 턴 길이(프레임 수). 알 수 없는 상태면 ValueError."""
    for a, head, b, tail in CONTEXT:
        if bytes(data[a:a + len(head)]) != head or bytes(data[b:b + len(tail)]) != tail:
            raise ValueError("턴 길이 패치: 지원하지 않는 게임 파일입니다.")
    frames, recover = data[FRAMES_SITE], data[RECOVER_SITE]
    if frames in CHOICES and recover in (2, 3):          # 예전 99ms 실험판은 (3, 3)
        return frames
    raise ValueError("턴 길이 패치: 알 수 없는 변경이 있습니다.")


def current(data, frames: int) -> bool:
    return state(data) == frames and data[RECOVER_SITE] == _recover(frames)


def transform(data, frames: int = ORIGINAL) -> bytes:
    if frames not in CHOICES:
        raise ValueError("턴 길이는 5, 3, 2 프레임 중 하나여야 합니다.")
    state(data)
    out = bytearray(data)
    out[FRAMES_SITE] = frames
    out[RECOVER_SITE] = _recover(frames)
    return bytes(out)
