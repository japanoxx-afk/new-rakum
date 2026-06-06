# RhakMu Start Sync Question for Claude Code

We are restoring the legacy RhakMu RTS multiplayer lobby with a dummy TCP server.

Current stable facts:

- Lobby login, room creation, room join, and room presence are stable again.
- The stable dummy server profile is now TCP-only and should not bind UDP 11223.
- When the host presses Start, only the host enters countdown/in-game.
- The guest does not start and later sends `0x11FF` leave-room after about 13 seconds.
- In earlier logs, the same 13-second leave happened even when `GameStartSyncMode=none`, so this is likely not caused only by the TCP `0x0FFF` relay payload.

Key uncertainty:

- Is the 13-second leave caused by direct client-to-client UDP 11223 handshake failure?
- Or is the client-side battle start patch entering the wrong state and bypassing/poisoning the original peer readiness flow?

Relevant scripts:

- `Start-RhakMuDummyServer.ps1`
- `Start-RhakMuStableServer.ps1`
- `Patch-RhakMuBattleStartSync.ps1`
- `Verify-RhakMuClientPatches.ps1`
- `Restore-RhakMuBattleStartSync.ps1`
- `Install-RhakMuClientPatches.ps1`

Current battle start patch:

- Patches `Rhakmu.exe` at VA `0x0044D2E2`, inside `TNPacket_ReplyBattleReqReply`.
- The host start relay packet `FF 0F 07 00 02 00 00` reaches the default branch because `packet[5] == 0`.
- The latest safer patch only sets:

```asm
mov byte ptr [0x006DFC74], 5
pop edi
pop esi
pop ebx
mov esp, ebp
pop ebp
ret
```

- It intentionally no longer writes `0x006E0970 = 0`.

Please analyze:

1. Is VA `0x0044D2E2` the right branch to patch for guest countdown on a relayed host start packet?
2. Does setting only `[0x006DFC74] = 5` correctly mimic the original guest countdown path, or are other room/player/seed fields required?
3. What exact client state does the original `classRoomNetMGR::RMPKRecv_GameStart` set before countdown?
4. What function sends `0x11FF` after about 13 seconds, and which condition/timer triggers it?
5. Which UDP packet or memory flag proves that the client-to-client peer handshake succeeded?
6. What x64dbg/Ghidra breakpoints should be used to prove whether the guest:
   - receives `0x0FFF`,
   - enters the patched branch,
   - sets countdown state,
   - fails UDP readiness,
   - sends `0x11FF`?

Suggested break/watch points:

- VA `0x0044D2E2` - patched `TNPacket_ReplyBattleReqReply` default branch.
- `0x006DFC74` - countdown/battle state.
- `0x006E0970` - start seed.
- Any caller of the TCP send path that emits packet type `0x11FF`.
- Any UDP send/recv wrapper in `TG_Net.dll` / `Rhakmu.exe` around port 11223.
