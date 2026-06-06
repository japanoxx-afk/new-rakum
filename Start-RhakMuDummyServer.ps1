param(
    [string]$Bind = "0.0.0.0",
    [int[]]$Ports = @(80, 11223, 2000, 2300, 2301, 2302, 2303, 2304, 2400, 3000, 4000, 47624, 5000, 7000, 7777, 8000, 8080, 9000, 10000, 10001, 10262, 11000, 12000, 20000, 21000, 28000),
    [ValidateSet("none", "empty", "guess")]
    [string]$AutoReply = "guess",
    [string]$LogDir = ".\rhakmu_packet_logs",
    [int]$TickMs = 25,
    [int]$CheckClientResult = 0,
    [ValidateSet("same", "plus1", "or8000")]
    [string]$CheckClientReplyType = "same",
    [ValidateSet("zero32", "empty", "text", "multi")]
    [string]$AnnouncementReplyMode = "zero32",
    [string]$TestAccount = "test",
    [string]$TestPassword = "test1234",
    [int]$LoginResult = 0,
    [ValidateSet("same", "plus1", "multi")]
    [string]$LoginReplyType = "same",
    [int]$ChannelJoinResult = 0,
    [ValidateSet("same", "plus1", "multi")]
    [string]$ChannelJoinReplyType = "same",
    [ValidateSet("ignore", "rank-empty", "guild-empty-a", "guild-empty-b", "all-empty")]
    [string]$GuildReplyMode = "guild-empty-a",
    [ValidateSet("ignore", "rank-empty", "guild-empty-a", "guild-empty-b", "all-empty", "zero32", "empty", "multi")]
    [string]$RankListReplyMode = "rank-empty",
    [ValidateSet("ignore", "empty")]
    [string]$RoomListReplyMode = "empty",
    [int]$RoomMakeResult = 0,
    [switch]$SendRoomJoinAfterMake,
    [string]$RoomJoinHost = "127.0.0.1",
    [string[]]$RoomHostOverrides = @(),
    [ValidateSet("ignore", "empty", "members")]
    [string]$ChannelUserListReplyMode = "members",
    [int[]]$SkipUdpPorts = @(11223),
    [string]$TranscriptPath = ".\rhakmu_dummy_server_terminal.log",
    [string]$EventLogPath = ".\rhakmu_dummy_server_events.log",
    [bool]$EnableUdpRelay = $true,
    [ValidateSet("none", "original", "original-plus-accept", "accept-only", "original-plus-variants")]
    [string]$GameStartSyncMode = "original",
    [switch]$AcceptLikelyAccountPackets
)

$ErrorActionPreference = "Stop"

function Get-NowStamp {
    return (Get-Date).ToString("yyyy-MM-dd HH:mm:ss.fff")
}

function Get-FileStamp {
    return (Get-Date).ToString("yyyyMMdd_HHmmss_fff")
}

function Add-ServerEvent([string]$Message) {
    if (-not [string]::IsNullOrWhiteSpace($script:ResolvedEventLogPath)) {
        try {
            Add-Content -LiteralPath $script:ResolvedEventLogPath -Value $Message -Encoding UTF8
        } catch {}
    }
}

function Write-ServerEvent(
    [string]$Message,
    [ConsoleColor]$ForegroundColor = [ConsoleColor]::Gray
) {
    Write-Host $Message -ForegroundColor $ForegroundColor
    Add-ServerEvent $Message
}

function Format-HexDump([byte[]]$Data) {
    $lines = New-Object System.Collections.Generic.List[string]
    for ($i = 0; $i -lt $Data.Length; $i += 16) {
        $chunkLen = [Math]::Min(16, $Data.Length - $i)
        $hex = New-Object System.Collections.Generic.List[string]
        $asc = New-Object System.Text.StringBuilder
        for ($j = 0; $j -lt $chunkLen; $j++) {
            $x = $Data[$i + $j]
            $hex.Add(("{0:X2}" -f $x))
            if ($x -ge 32 -and $x -le 126) {
                [void]$asc.Append([char]$x)
            } else {
                [void]$asc.Append(".")
            }
        }
        $lines.Add(("{0:X4}  {1,-48}  {2}" -f $i, ($hex -join " "), $asc.ToString()))
    }
    return ($lines -join [Environment]::NewLine)
}

function Get-AsciiStrings([byte[]]$Data, [int]$MinLen = 3) {
    $out = New-Object System.Collections.Generic.List[string]
    $buf = New-Object System.Collections.Generic.List[byte]
    foreach ($x in $Data) {
        if ($x -ge 32 -and $x -le 126) {
            $buf.Add($x)
        } else {
            if ($buf.Count -ge $MinLen) {
                $out.Add([Text.Encoding]::ASCII.GetString($buf.ToArray()))
            }
            $buf.Clear()
        }
    }
    if ($buf.Count -ge $MinLen) {
        $out.Add([Text.Encoding]::ASCII.GetString($buf.ToArray()))
    }
    return $out
}

function Get-PacketPayload([byte[]]$Packet) {
    if ($Packet.Length -le 4) { return [byte[]]@() }
    $payload = New-Object byte[] ($Packet.Length - 4)
    [Array]::Copy($Packet, 4, $payload, 0, $payload.Length)
    return $payload
}

function Test-LikelyAccountPacket([byte[]]$Packet) {
    if ($Packet.Length -lt 8) { return $false }
    $reqType = Read-U16LE $Packet 0
    $payload = Get-PacketPayload $Packet
    $ascii = Get-AsciiStrings $payload 2
    $payloadText = [Text.Encoding]::ASCII.GetString($payload)

    if ($payloadText -match [regex]::Escape($script:TestAccount)) { return $true }
    if ($payloadText -match [regex]::Escape($script:TestPassword)) { return $true }
    if ($ascii.Count -ge 2 -and ($reqType -band 0x00FF) -eq 0x00FF) { return $true }
    return $false
}

function Get-NulTerminatedStrings([byte[]]$Data, [int]$MinLen = 0) {
    $out = New-Object System.Collections.Generic.List[string]
    $buf = New-Object System.Collections.Generic.List[byte]
    foreach ($x in $Data) {
        if ($x -eq 0) {
            if ($buf.Count -ge $MinLen) {
                $out.Add([Text.Encoding]::Default.GetString($buf.ToArray()))
            }
            $buf.Clear()
        } else {
            $buf.Add($x)
        }
    }
    if ($buf.Count -ge $MinLen) {
        $out.Add([Text.Encoding]::Default.GetString($buf.ToArray()))
    }
    return $out
}

function Get-LoginFields([byte[]]$Packet) {
    $strings = Get-NulTerminatedStrings (Get-PacketPayload $Packet) 1
    $account = ""
    $password = ""
    if ($strings.Count -ge 1) { $account = $strings[0] }
    if ($strings.Count -ge 2) { $password = $strings[1] }
    return [pscustomobject]@{
        Account = $account
        Password = $password
    }
}

function Test-RhakMuLogin([byte[]]$Packet) {
    $fields = Get-LoginFields $Packet
    if ([string]::IsNullOrWhiteSpace($fields.Account)) { return 1 }
    if (-not $script:Accounts.ContainsKey($fields.Account)) { return 1 }
    if ($script:Accounts[$fields.Account] -ne $fields.Password) { return 2 }
    return 0
}

function Read-U16LE([byte[]]$Data, [int]$Offset) {
    return [BitConverter]::ToUInt16($Data, $Offset)
}

function New-TgPacket([uint16]$Type, [byte[]]$Payload) {
    if ($null -eq $Payload) { $Payload = [byte[]]@() }
    $size = 4 + $Payload.Length
    $out = New-Object byte[] $size
    [BitConverter]::GetBytes([uint16]$Type).CopyTo($out, 0)
    [BitConverter]::GetBytes([uint16]$size).CopyTo($out, 2)
    if ($Payload.Length -gt 0) { $Payload.CopyTo($out, 4) }
    return $out
}

function New-ReplyPackets([uint16]$ReqType, [string]$Mode) {
    $replies = New-Object System.Collections.Generic.List[byte[]]
    if ($Mode -eq "none") { return ,$replies }

    if ($Mode -eq "empty") {
        $replies.Add((New-TgPacket $ReqType ([byte[]]@())))
        return ,$replies
    }

    $ok1 = [BitConverter]::GetBytes([uint32]1)
    $ok0 = [BitConverter]::GetBytes([uint32]0)
    $replies.Add((New-TgPacket $ReqType $ok1))
    $replies.Add((New-TgPacket ([uint16](($ReqType + 1) -band 0xFFFF)) $ok1))
    $replies.Add((New-TgPacket ([uint16]($ReqType -bor 0x8000)) $ok1))
    $replies.Add((New-TgPacket $ReqType $ok0))
    return ,$replies
}

function Test-SkipAutoReply([uint16]$ReqType) {
    return ($ReqType -eq 0x0BFF -or $ReqType -eq 0x0EFF -or $ReqType -eq 0x0FFF -or $ReqType -eq 0x10FF -or $ReqType -eq 0x1FFF -or $ReqType -eq 0x15FF -or $ReqType -eq 0x18FF -or $ReqType -eq 0x24FF -or $ReqType -eq 0x27FF -or $ReqType -eq 0x12FF)
}

function Get-ConnectionKey([int]$Port, [string]$Peer) {
    return "$Port|$Peer"
}

function Add-EmptyLobbyListReplies(
    [System.Collections.Generic.List[byte[]]]$Replies,
    [string]$Mode
) {
    $empty = [byte[]]@()
    switch ($Mode) {
        "rank-empty" {
            $Replies.Add((New-TgPacket 0x16FF $empty))
            $Replies.Add((New-TgPacket 0x17FF $empty))
        }
        "guild-empty-a" {
            $Replies.Add((New-TgPacket 0x19FF $empty))
            $Replies.Add((New-TgPacket 0x1AFF $empty))
        }
        "guild-empty-b" {
            $Replies.Add((New-TgPacket 0x1CFF $empty))
            $Replies.Add((New-TgPacket 0x1DFF $empty))
        }
        "all-empty" {
            $Replies.Add((New-TgPacket 0x16FF $empty))
            $Replies.Add((New-TgPacket 0x17FF $empty))
            $Replies.Add((New-TgPacket 0x19FF $empty))
            $Replies.Add((New-TgPacket 0x1AFF $empty))
            $Replies.Add((New-TgPacket 0x1CFF $empty))
            $Replies.Add((New-TgPacket 0x1DFF $empty))
        }
    }
}

function New-NulStringBytes([string]$Text) {
    if ($null -eq $Text) { $Text = "" }
    return [Text.Encoding]::ASCII.GetBytes($Text + "`0")
}

function Join-ByteArrays([byte[][]]$Parts) {
    $total = 0
    foreach ($part in $Parts) {
        if ($null -ne $part) { $total += $part.Length }
    }
    $out = New-Object byte[] $total
    $offset = 0
    foreach ($part in $Parts) {
        if ($null -ne $part -and $part.Length -gt 0) {
            [Array]::Copy($part, 0, $out, $offset, $part.Length)
            $offset += $part.Length
        }
    }
    return $out
}

function New-RoomJoinOkPayload {
    $result = [byte[]]@([byte]0)
    $account = New-NulStringBytes $script:TestAccount
    $hostBytes = New-NulStringBytes $script:RoomJoinHost
    return Join-ByteArrays @($result, $account, $hostBytes)
}

function Get-PeerHost([string]$Peer) {
    if ($Peer -match '^\[([^\]]+)\]:(\d+)$') { return $Matches[1] }
    if ($Peer -match '^(.+):(\d+)$') { return $Matches[1] }
    return $Peer
}

function Get-PreferredRoomJoinHost {
    try {
        $addresses = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
            Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' }

        $vpn = $addresses | Where-Object { $_.InterfaceAlias -match 'Radmin|Hamachi|ZeroTier|Tailscale|VPN' } | Select-Object -First 1
        if ($null -ne $vpn) { return $vpn.IPAddress }

        $lan = $addresses | Where-Object { $_.IPAddress -like '192.168.*' -or $_.IPAddress -like '10.*' -or $_.IPAddress -like '172.*' } | Select-Object -First 1
        if ($null -ne $lan) { return $lan.IPAddress }
    } catch {}

    return "127.0.0.1"
}

function Resolve-RoomHost([string]$PeerHost) {
    if ([string]::IsNullOrWhiteSpace($PeerHost)) { return $script:RoomJoinHost }
    if ($PeerHost -eq "127.0.0.1" -or $PeerHost -eq "localhost" -or $PeerHost -eq "::1") {
        return $script:RoomJoinHost
    }
    return $PeerHost
}

function Get-RoomHostForAccount([string]$Account, [string]$FallbackHost) {
    if (-not [string]::IsNullOrWhiteSpace($Account) -and $script:RoomHostOverrideMap.ContainsKey($Account)) {
        return $script:RoomHostOverrideMap[$Account]
    }
    return $FallbackHost
}

function New-RoomJoinPayload([string]$Account, [string]$HostAddress) {
    if ([string]::IsNullOrWhiteSpace($Account)) { $Account = $script:TestAccount }
    if ([string]::IsNullOrWhiteSpace($HostAddress)) { $HostAddress = $script:RoomJoinHost }
    $HostAddress = Get-RoomHostForAccount $Account $HostAddress
    $result = [byte[]]@([byte]0)
    $accountBytes = New-NulStringBytes $Account
    $hostBytes = New-NulStringBytes $HostAddress
    return Join-ByteArrays @($result, $accountBytes, $hostBytes)
}

function New-RoomFromCreatePacket([byte[]]$Packet) {
    $payload = Get-PacketPayload $Packet
    $strings = Get-AsciiStrings $payload 2
    $title = ""
    $map = ""
    $owner = $script:CurrentAccount
    if ($strings.Count -ge 1) { $title = $strings[0] }
    if ($strings.Count -ge 2) { $map = $strings[1] }
    if ($strings.Count -ge 3 -and -not [string]::IsNullOrWhiteSpace($strings[2])) { $owner = $strings[2] }
    if ([string]::IsNullOrWhiteSpace($owner)) { $owner = $script:TestAccount }

    return [pscustomobject]@{
        Id = $script:NextRoomId
        Title = $title
        Map = $map
        Owner = $owner
        Host = (Get-RoomHostForAccount $owner (Resolve-RoomHost $script:CurrentHost))
        MaxPlayers = (Get-RoomMaxPlayersFromCreatePayload $payload)
        ItemPayload = $payload
        RoomMembers = (New-Object System.Collections.Generic.List[object])
        CreatedAt = Get-Date
    }
}

function Ensure-RoomMembers([object]$Room) {
    if ($null -eq $Room) { return $null }
    if ($null -eq $Room.PSObject.Properties["RoomMembers"]) {
        $Room | Add-Member -NotePropertyName RoomMembers -NotePropertyValue (New-Object System.Collections.Generic.List[object])
    }
    Write-Output -NoEnumerate $Room.RoomMembers
}

function Add-RoomMember([object]$Room, [string]$Account, [string]$HostAddress) {
    if ($null -eq $Room -or [string]::IsNullOrWhiteSpace($Account)) { return }
    if ([string]::IsNullOrWhiteSpace($HostAddress)) { $HostAddress = $script:RoomJoinHost }
    $HostAddress = Get-RoomHostForAccount $Account $HostAddress

    $members = Ensure-RoomMembers $Room
    foreach ($member in @($members.ToArray())) {
        if ($member.Account -eq $Account) {
            [void]$members.Remove($member)
        }
    }

    $members.Add([pscustomobject]@{
        Account = $Account
        Host = $HostAddress
    })
}

function Remove-RoomMember([object]$Room, [string]$Account) {
    if ($null -eq $Room -or [string]::IsNullOrWhiteSpace($Account)) { return }
    $members = Ensure-RoomMembers $Room
    foreach ($member in @($members.ToArray())) {
        if ($member.Account -eq $Account) {
            [void]$members.Remove($member)
        }
    }
}

function Remove-StaleConnectionsForAccount(
    [string]$Account,
    [object]$CurrentConn
) {
    if ([string]::IsNullOrWhiteSpace($Account)) { return }

    foreach ($target in @($script:Clients.ToArray())) {
        if ($null -eq $target) { continue }
        if ($null -ne $CurrentConn -and $target.Peer -eq $CurrentConn.Peer -and $target.Port -eq $CurrentConn.Port) { continue }
        if ($target.Account -ne $Account) { continue }

        $roomTitle = $target.RoomTitle
        if (-not [string]::IsNullOrWhiteSpace($roomTitle)) {
            $room = Find-RoomByTitle $roomTitle
            if ($null -ne $room) {
                Remove-RoomMember $room $Account
            }
        }

        try { $target.Stream.Close() } catch {}
        try { $target.Client.Close() } catch {}
        [void]$script:Clients.Remove($target)

        $now = Get-NowStamp
        Write-ServerEvent "[$now] Stale client connection removed account=$Account peer=$($target.Peer) room=$roomTitle" ([ConsoleColor]::DarkYellow)
    }
}

function Get-RoomMemberCount([object]$Room) {
    if ($null -eq $Room) { return 1 }
    $members = Ensure-RoomMembers $Room
    if ($null -ne $members -and $members.Count -gt 0) {
        return [Math]::Max(1, [Math]::Min(8, [int]$members.Count))
    }
    return 1
}

function Get-RoomMaxPlayersFromCreatePayload([byte[]]$Payload) {
    if ($Payload.Length -ge 6) {
        $max = [BitConverter]::ToUInt16($Payload, 4)
        if ($max -gt 0 -and $max -le 8) { return [int]$max }
    }
    return 4
}

function New-ServerRoomListPayload([object]$Room) {
    $roomName = if ([string]::IsNullOrWhiteSpace($Room.Title)) { $Room.Owner } else { $Room.Title }
    $hostName = if ([string]::IsNullOrWhiteSpace($Room.Host)) { $script:RoomJoinHost } else { $Room.Host }
    $maxPlayers = [Math]::Max(1, [Math]::Min(8, [int]$Room.MaxPlayers))
    $currentPlayers = Get-RoomMemberCount $Room

    # TNPacket_ReplyRoomList reads one room as:
    #   10-byte server-room header,
    #   NUL-terminated room name,
    #   ROOM_DATA bytes whose length is header[8..9].
    # ROOM_DATA begins with 9 bytes of compact room metadata and then the
    # NUL-terminated room IP/host string.
    $roomData = Join-ByteArrays @(
        ([byte[]]@(
            0x00,
            0x88, 0x00,
            0x88, 0x00,
            0x00,
            [byte]$currentPlayers,
            [byte]$maxPlayers,
            0x00
        )),
        (New-NulStringBytes $hostName)
    )

    $header = New-Object byte[] 10
    $header[0] = 0
    $header[1] = 0
    $header[2] = 1
    $header[3] = 0
    [BitConverter]::GetBytes([uint16]$currentPlayers).CopyTo($header, 4)
    [BitConverter]::GetBytes([uint16]$maxPlayers).CopyTo($header, 6)
    [BitConverter]::GetBytes([uint16]$roomData.Length).CopyTo($header, 8)

    return Join-ByteArrays @($header, (New-NulStringBytes $roomName), $roomData)
}

function New-ServerChannelUserPayload([string]$Account, [string]$HostAddress) {
    if ([string]::IsNullOrWhiteSpace($Account)) { $Account = $script:TestAccount }
    if ([string]::IsNullOrWhiteSpace($HostAddress)) { $HostAddress = $script:RoomJoinHost }

    # The exact t_server_channeluser_reply layout is still being recovered.
    # The client-side helpers expose account and server IP strings, and this
    # packet family uses TG_Net string packing elsewhere, so keep the payload
    # conservative: account plus host, both NUL terminated.
    return Join-ByteArrays @(
        (New-NulStringBytes $Account),
        (New-NulStringBytes $HostAddress)
    )
}

function Add-ChannelUserListReplies(
    [System.Collections.Generic.List[byte[]]]$Replies,
    [object]$Room
) {
    $Replies.Add((New-TgPacket 0x20FF ([byte[]]@())))

    $members = Ensure-RoomMembers $Room
    if ($null -ne $members -and $members.Count -gt 0) {
        foreach ($member in $members.ToArray()) {
            $Replies.Add((New-TgPacket 0x1FFF (New-ServerChannelUserPayload $member.Account $member.Host)))
        }
    } elseif (-not [string]::IsNullOrWhiteSpace($script:CurrentAccount)) {
        $Replies.Add((New-TgPacket 0x1FFF (New-ServerChannelUserPayload $script:CurrentAccount (Resolve-RoomHost $script:CurrentHost))))
    }

    $Replies.Add((New-TgPacket 0x21FF ([byte[]]@())))
}

function New-ServerMessagePayload([string]$Message, [string]$Account) {
    if ([string]::IsNullOrWhiteSpace($Account)) { $Account = "server" }
    if ($null -eq $Message) { $Message = "" }
    return Join-ByteArrays @(
        ([byte[]]@([byte]0, 0x00, 0x00)),
        (New-NulStringBytes $Account),
        (New-NulStringBytes $Message)
    )
}

function Register-RoomFromCreatePacket([byte[]]$Packet) {
    $room = New-RoomFromCreatePacket $Packet
    $oldAccount = $script:CurrentAccount
    $oldHost = $script:CurrentHost
    $script:CurrentAccount = $room.Owner
    $script:CurrentHost = $room.Host
    [void](Remove-RoomsForCurrentClient)
    $script:CurrentAccount = $oldAccount
    $script:CurrentHost = $oldHost

    $script:NextRoomId++
    Add-RoomMember $room $room.Owner $room.Host
    $script:Rooms.Add($room)
    $now = Get-NowStamp
    Write-Host "[$now] Room registered id=$($room.Id) title=$($room.Title) map=$($room.Map) owner=$($room.Owner) host=$($room.Host)" -ForegroundColor Green
    return $room
}

function Find-RoomForJoin([byte[]]$Packet) {
    $payload = Get-PacketPayload $Packet
    $strings = Get-NulTerminatedStrings $payload 1
    $wanted = ""
    if ($strings.Count -ge 1) { $wanted = $strings[0] }

    $last = $null
    foreach ($room in $script:Rooms) {
        $last = $room
        if ($room.Title -eq $wanted -or $room.Owner -eq $wanted -or $room.Map -eq $wanted) {
            return $room
        }
    }
    return $last
}

function Find-RoomForAccount([string]$Account) {
    if ([string]::IsNullOrWhiteSpace($Account)) { return $null }
    foreach ($room in $script:Rooms) {
        if ($room.Owner -eq $Account) { return $room }
        $members = Ensure-RoomMembers $room
        foreach ($member in @($members.ToArray())) {
            if ($member.Account -eq $Account) { return $room }
        }
    }
    return $null
}

function Resolve-ConnectionRoomTitle([object]$Conn) {
    if ($null -eq $Conn) { return "" }
    if (-not [string]::IsNullOrWhiteSpace($Conn.RoomTitle)) { return $Conn.RoomTitle }

    $room = Find-RoomForAccount $Conn.Account
    if ($null -ne $room) {
        $Conn.RoomTitle = $room.Title
        $now = Get-NowStamp
        Write-ServerEvent "[$now] Connection room inferred peer=$($Conn.Peer) account=$($Conn.Account) room=$($Conn.RoomTitle)" ([ConsoleColor]::DarkGreen)
        return $Conn.RoomTitle
    }

    return ""
}

function Find-RoomByTitle([string]$Title) {
    if ([string]::IsNullOrWhiteSpace($Title)) { return $null }
    foreach ($room in $script:Rooms) {
        if ($room.Title -eq $Title) { return $room }
    }
    return $null
}

function Test-PostGameRoomReentryPacket([byte[]]$Packet) {
    if ([string]::IsNullOrWhiteSpace($script:CurrentRoomTitle)) { return $false }

    $payload = Get-PacketPayload $Packet
    if ($payload.Length -lt 3 -or $payload[0] -ne 0) { return $false }

    $strings = Get-NulTerminatedStrings $payload 1
    if ($strings.Count -lt 1) { return $false }

    return ($strings[0] -match '^\d+$')
}

function Remove-RoomsForCurrentClient {
    $account = $script:CurrentAccount
    $roomHost = Resolve-RoomHost $script:CurrentHost
    $removed = 0

    foreach ($room in @($script:Rooms.ToArray())) {
        $ownedByAccount = (-not [string]::IsNullOrWhiteSpace($account) -and $room.Owner -eq $account)
        $ownedByHost = (-not [string]::IsNullOrWhiteSpace($roomHost) -and $room.Host -eq $roomHost)
        if ($ownedByAccount -or $ownedByHost) {
            [void]$script:Rooms.Remove($room)
            $removed++
            $now = Get-NowStamp
            Write-Host "[$now] Room removed id=$($room.Id) title=$($room.Title) owner=$($room.Owner) host=$($room.Host)" -ForegroundColor Green
        }
    }

    return $removed
}

function New-ByteNulPayload([byte]$Value) {
    return [byte[]]@($Value, 0)
}

function New-RhakMuProtocolReplies([byte[]]$Packet) {
    $replies = New-Object System.Collections.Generic.List[byte[]]
    if ($Packet.Length -lt 4) { return ,$replies }

    $reqType = Read-U16LE $Packet 0
    $payload = Get-PacketPayload $Packet

    # First observed online handshake:
    # FF 01 0C 00 52 48 41 4B E8 03 00 00
    # type=0x01FF, size=12, payload="RHAK" + uint32 1000.
    if ($reqType -eq 0x01FF) {
        $payload = [BitConverter]::GetBytes([uint32]$script:CheckClientResult)
        $replyType = switch ($script:CheckClientReplyType) {
            "plus1" { [uint16]0x0200 }
            "or8000" { [uint16]0x81FF }
            default { [uint16]0x01FF }
        }
        $replies.Add((New-TgPacket $replyType $payload))
    }

    # Observed immediately after check-client success while the UI shows
    # "requesting announcement". Symbol table has TNPacket_ReqAnnounceMent
    # and TNPacket_ReplyAnnounceMent, so send a minimal "no announcement" reply.
    if ($reqType -eq 0x03FF) {
        if ($script:AnnouncementReplyMode -eq "empty") {
            $replies.Add((New-TgPacket 0x03FF ([byte[]]@())))
        } elseif ($script:AnnouncementReplyMode -eq "text") {
            $text = [Text.Encoding]::ASCII.GetBytes("RhakMu dummy server is online.`0")
            $replies.Add((New-TgPacket 0x03FF $text))
        } elseif ($script:AnnouncementReplyMode -eq "multi") {
            $replies.Add((New-TgPacket 0x03FF ([BitConverter]::GetBytes([uint32]0))))
            $replies.Add((New-TgPacket 0x03FF ([byte[]]@())))
            $text = [Text.Encoding]::ASCII.GetBytes("RhakMu dummy server is online.`0")
            $replies.Add((New-TgPacket 0x03FF $text))
            $replies.Add((New-TgPacket 0x0400 ([BitConverter]::GetBytes([uint32]0))))
        } else {
            $replies.Add((New-TgPacket 0x03FF ([BitConverter]::GetBytes([uint32]0))))
        }
    }

    # Observed after announcement request: type=0x02FF, size=6, payload=03 00.
    # Keep the connection moving with a tiny success ACK until the exact enum is known.
    if ($reqType -eq 0x02FF) {
        $replies.Add((New-TgPacket 0x02FF ([BitConverter]::GetBytes([uint32]0))))
    }

    # Observed login request:
    # type=0x05FF, payload="<id>\0<password>\0..."
    # Runtime string: "Server REPLY LoginAccount Result: %d" and "Login....OK".
    if ($reqType -eq 0x05FF) {
        $result = Test-RhakMuLogin $Packet
        $payload = [BitConverter]::GetBytes([uint32]$result)
        if ($script:LoginReplyType -eq "plus1") {
            $replies.Add((New-TgPacket 0x0600 $payload))
        } elseif ($script:LoginReplyType -eq "multi") {
            $replies.Add((New-TgPacket 0x05FF $payload))
            $replies.Add((New-TgPacket 0x0600 $payload))
            $replies.Add((New-TgPacket 0x85FF $payload))
        } else {
            $replies.Add((New-TgPacket 0x05FF $payload))
        }
    }

    # Observed after login while UI shows "connecting to channel".
    # type=0x07FF, payload="<channel name>\0".
    # Runtime string: Server REPLY Channel[ %s ] Join Result: %d.
    if ($reqType -eq 0x07FF) {
        $payload = [BitConverter]::GetBytes([uint32]$script:ChannelJoinResult)
        if ($script:ChannelJoinReplyType -eq "plus1") {
            $replies.Add((New-TgPacket 0x0800 $payload))
        } elseif ($script:ChannelJoinReplyType -eq "multi") {
            $replies.Add((New-TgPacket 0x07FF $payload))
            $replies.Add((New-TgPacket 0x0800 $payload))
            $replies.Add((New-TgPacket 0x87FF $payload))
        } else {
            $replies.Add((New-TgPacket 0x07FF $payload))
        }
    }

    # 0x15FF is a rank-list item reply on the client side. The client also
    # sends it as a request during lobby loading, so answer with rank
    # start/end only and never echo 0x15FF with a tiny payload.
    if ($reqType -eq 0x15FF -and $script:RankListReplyMode -ne "ignore") {
        $isInitialRankRequest = ($payload.Length -ge 9 -and $payload[0] -eq 1)
        if ($isInitialRankRequest -or -not $script:LobbyListReplySent.Contains($script:CurrentConnKey)) {
            Add-EmptyLobbyListReplies $replies $script:RankListReplyMode
            [void]$script:LobbyListReplySent.Add($script:CurrentConnKey)
        } else {
            $now = Get-NowStamp
            Write-Host "[$now] TCP suppress repeat rank-list reply peer=${script:CurrentConnKey}" -ForegroundColor DarkYellow
        }
    }

    # 0x18FF is a guild-list item reply on the client side. During lobby
    # loading the client sends it as the guild-list request, so reply with
    # guild-list start/end only.
    if ($reqType -eq 0x18FF -and $script:GuildReplyMode -ne "ignore") {
        if ($script:GuildReplyMode -in @("rank-empty", "guild-empty-a", "guild-empty-b", "all-empty")) {
            Add-EmptyLobbyListReplies $replies $script:GuildReplyMode
        } elseif ($script:GuildReplyMode -eq "empty") {
            $replies.Add((New-TgPacket $reqType ([byte[]]@())))
        } elseif ($script:GuildReplyMode -eq "multi") {
            $replies.Add((New-TgPacket $reqType ([byte[]]@())))
            $replies.Add((New-TgPacket ([uint16](($reqType + 1) -band 0xFFFF)) ([byte[]]@())))
        } else {
            $replies.Add((New-TgPacket $reqType ([BitConverter]::GetBytes([uint32]0))))
        }
    }

    # Observed when the lobby asks for the room list. Client handlers show:
    # 0x0CFF = RoomListStart, 0x0BFF = RoomListItem, 0x0DFF = RoomListEnd.
    # Send the rooms created during this server session.
    if ($reqType -eq 0x0BFF -and $script:RoomListReplyMode -eq "empty") {
        $replies.Add((New-TgPacket 0x0CFF ([byte[]]@())))
        foreach ($room in $script:Rooms) {
            $replies.Add((New-TgPacket 0x0BFF (New-ServerRoomListPayload $room)))
        }
        $replies.Add((New-TgPacket 0x0DFF ([byte[]]@())))
    }

    # Observed when pressing create room. 0x0EFF is also the client's room-make
    # result handler; byte 0 means OK in the client-side switch.
    if ($reqType -eq 0x0EFF) {
        $room = Register-RoomFromCreatePacket $Packet
        $replies.Add((New-TgPacket 0x0EFF ([BitConverter]::GetBytes([uint32]$script:RoomMakeResult))))
        if ($script:RoomMakeResult -eq 0 -and $script:SendRoomJoinAfterMake) {
            $replies.Add((New-TgPacket 0x10FF (New-RoomJoinPayload $room.Owner $room.Host)))
        }
    }

    # Observed when joining an existing room manually from the battlefield list.
    # Request payload looks like "<room title or owner>\0<password/flag>\0".
    if ($reqType -eq 0x10FF) {
        if (Test-PostGameRoomReentryPacket $Packet) {
            $now = Get-NowStamp
            Write-Host "[$now] TCP suppress post-game room reentry reply peer=${script:CurrentConnKey} account=${script:CurrentAccount} room=${script:CurrentRoomTitle}" -ForegroundColor DarkYellow
        } else {
            $room = Find-RoomForJoin $Packet
            if ($null -eq $room) {
                $replies.Add((New-TgPacket 0x10FF ([BitConverter]::GetBytes([uint32]1))))
            } else {
                # The first string in the room-join reply is treated as the room host
                # identity by the client-side room/game setup. Sending the joining
                # account here can flip the local player slot at game start.
                $replies.Add((New-TgPacket 0x10FF (New-RoomJoinPayload $room.Owner $room.Host)))
            }
        }
    }

    # Observed when the room host leaves/cancels a created room.
    # Remove the server-side room entry so later battlefield refreshes no
    # longer return a stale room.
    if ($reqType -eq 0x11FF) {
        [void](Remove-RoomsForCurrentClient)
    }

    # Observed after room creation and room join. Client handlers show:
    # 0x20FF = ChannelUserListStart, 0x1FFF = ChannelUserListItem,
    # 0x21FF = ChannelUserListEnd.
    if ($reqType -eq 0x1FFF -and $script:ChannelUserListReplyMode -eq "empty") {
        $replies.Add((New-TgPacket 0x20FF ([byte[]]@())))
        $replies.Add((New-TgPacket 0x21FF ([byte[]]@())))
    }

    if ($reqType -eq 0x1FFF -and $script:ChannelUserListReplyMode -eq "members") {
        $room = Find-RoomByTitle $script:CurrentRoomTitle
        if ($null -ne $room) {
            Add-ChannelUserListReplies $replies $room
        } else {
            $replies.Add((New-TgPacket 0x20FF ([byte[]]@())))
            $replies.Add((New-TgPacket 0x21FF ([byte[]]@())))
        }
    }

    # Observed around battle/game cleanup. 0x24FF tolerates a compact 0x25FF
    # result. 0x27FF is different: replying with 0x26FF 02 00 can route the
    # client through TNPacket_ReplyBattleReqReply -> TNPacket_ReqRoomJoin and
    # crash in classSTB::SetIndexPosition while returning from the match.
    if ($reqType -eq 0x24FF) {
        $replies.Add((New-TgPacket 0x25FF (New-ByteNulPayload 2)))
    }

    if ($reqType -eq 0x27FF) {
        $now = Get-NowStamp
        Write-Host "[$now] TCP suppress 0x27FF cleanup reply peer=${script:CurrentConnKey} account=${script:CurrentAccount} room=${script:CurrentRoomTitle}" -ForegroundColor DarkYellow
    }

    # Observed lobby chat request:
    # type=0x12FF, payload="<message>\0<account>\0".
    # The client does not keep the message locally; it expects the server to
    # echo/broadcast it back as a lobby chat packet.
    if ($reqType -eq 0x12FF) {
        $chatParts = Get-NulTerminatedStrings $payload 1
        $chatMessage = ""
        $chatAccount = $script:CurrentAccount
        if ($chatParts.Count -ge 1) { $chatMessage = $chatParts[0] }
        if ($chatParts.Count -ge 2) { $chatAccount = $chatParts[1] }
        $serverMsgPayload = New-ServerMessagePayload $chatMessage $chatAccount
        $replies.Add((New-TgPacket 0x13FF $serverMsgPayload))
    }

    # Login/create-account phase is not fully mapped yet. This accepts the
    # built-in test account and any account-looking packet so the next screen
    # can reveal channel/room packet IDs.
    if ($script:AcceptLikelyAccountPackets -and (Test-LikelyAccountPacket $Packet)) {
        $payload0 = [BitConverter]::GetBytes([uint32]0)
        $payload1 = [BitConverter]::GetBytes([uint32]1)
        $replies.Add((New-TgPacket $reqType $payload0))
        $replies.Add((New-TgPacket $reqType $payload1))
        $replies.Add((New-TgPacket ([uint16](($reqType + 1) -band 0xFFFF)) $payload0))
    }

    return ,$replies
}

function Test-HttpRequest([byte[]]$Data) {
    if ($Data.Length -lt 3) { return $false }
    $prefix = [Text.Encoding]::ASCII.GetString($Data, 0, [Math]::Min($Data.Length, 8))
    return ($prefix.StartsWith("GET ") -or $prefix.StartsWith("HEAD ") -or $prefix.StartsWith("POST "))
}

function New-HttpReply([byte[]]$Data) {
    $request = [Text.Encoding]::ASCII.GetString($Data, 0, $Data.Length)
    $firstLine = ($request -split "`r?`n" | Select-Object -First 1)
    $path = "/"
    if ($firstLine -match '^[A-Z]+\s+(\S+)') { $path = $Matches[1] }

    $body = @"
RhakMu dummy patch server
status=ok
path=$path
version=1.000
"@
    $bodyBytes = [Text.Encoding]::ASCII.GetBytes($body)
    $header = "HTTP/1.1 200 OK`r`nServer: RhakMuDummy`r`nContent-Type: text/plain`r`nContent-Length: $($bodyBytes.Length)`r`nConnection: close`r`n`r`n"
    $headerBytes = [Text.Encoding]::ASCII.GetBytes($header)
    $out = New-Object byte[] ($headerBytes.Length + $bodyBytes.Length)
    $headerBytes.CopyTo($out, 0)
    $bodyBytes.CopyTo($out, $headerBytes.Length)
    return $out
}

function Split-TgPackets([byte[]]$Data) {
    $packets = New-Object System.Collections.Generic.List[byte[]]
    $offset = 0
    while ($offset + 4 -le $Data.Length) {
        $size = Read-U16LE $Data ($offset + 2)
        if ($size -ge 4 -and $size -le 4096 -and ($offset + $size) -le $Data.Length) {
            $packet = New-Object byte[] $size
            [Array]::Copy($Data, $offset, $packet, 0, $size)
            $packets.Add($packet)
            $offset += $size
        } else {
            $rest = $Data.Length - $offset
            $packet = New-Object byte[] $rest
            [Array]::Copy($Data, $offset, $packet, 0, $rest)
            $packets.Add($packet)
            break
        }
    }
    if ($packets.Count -eq 0 -and $Data.Length -gt 0) {
        $packets.Add($Data)
    }
    return $packets
}

function Split-TgStream([byte[]]$Data) {
    $packets = New-Object System.Collections.Generic.List[byte[]]
    $offset = 0

    while ($offset + 4 -le $Data.Length) {
        $size = Read-U16LE $Data ($offset + 2)
        if ($size -ge 4 -and $size -le 4096) {
            if (($offset + $size) -gt $Data.Length) { break }
            $packet = New-Object byte[] $size
            [Array]::Copy($Data, $offset, $packet, 0, $size)
            $packets.Add($packet)
            $offset += $size
        } else {
            $rest = $Data.Length - $offset
            $packet = New-Object byte[] $rest
            [Array]::Copy($Data, $offset, $packet, 0, $rest)
            $packets.Add($packet)
            $offset = $Data.Length
            break
        }
    }

    $remainingLen = $Data.Length - $offset
    $remaining = New-Object byte[] $remainingLen
    if ($remainingLen -gt 0) {
        [Array]::Copy($Data, $offset, $remaining, 0, $remainingLen)
    }

    return [pscustomobject]@{
        Packets = $packets
        Remaining = $remaining
    }
}

function Save-PacketLog(
    [string]$Proto,
    [int]$Port,
    [string]$Peer,
    [byte[]]$Data
) {
    $typeText = "raw"
    $sizeText = $Data.Length
    if ($Data.Length -ge 4) {
        $pktType = Read-U16LE $Data 0
        $pktSize = Read-U16LE $Data 2
        $typeText = "0x{0:X4}({1})" -f $pktType, $pktType
        $sizeText = $pktSize
    }

    $safePeer = ($Peer -replace '[^\w.-]', '_')
    $fileStamp = Get-FileStamp
    $baseName = "${fileStamp}_${Proto}_${Port}_${safePeer}"
    $base = Join-Path $script:ResolvedLogDir $baseName
    [IO.File]::WriteAllBytes("$base.bin", $Data)

    $ascii = Get-AsciiStrings $Data
    $text = New-Object System.Collections.Generic.List[string]
    $now = Get-NowStamp
    $text.Add("[$now] $Proto port=$Port peer=$Peer type=$typeText size=$sizeText raw_len=$($Data.Length)")
    if ($ascii.Count -gt 0) { $text.Add("ASCII: " + (($ascii | Select-Object -First 20) -join " | ")) }
    $text.Add("")
    $text.Add((Format-HexDump $Data))
    $text | Set-Content -LiteralPath "$base.txt" -Encoding UTF8

    Write-Host ""
    $upperProto = $Proto.ToUpperInvariant()
    $summary = "[$now] $upperProto port=$Port peer=$Peer type=$typeText size=$sizeText raw_len=$($Data.Length)"
    Write-Host $summary -ForegroundColor Cyan
    Add-ServerEvent $summary
    if ($ascii.Count -gt 0) {
        $asciiLine = "ASCII: " + (($ascii | Select-Object -First 8) -join " | ")
        Write-Host $asciiLine -ForegroundColor DarkCyan
        Add-ServerEvent $asciiLine
    }
    Write-Host (Format-HexDump $Data)
}

function Send-TcpPacket(
    [object]$Conn,
    [byte[]]$Packet,
    [string]$Proto = "tcp-reply"
) {
    $Conn.Stream.Write($Packet, 0, $Packet.Length)
    Save-PacketLog $Proto $Conn.Port $Conn.Peer $Packet
    $rtype = Read-U16LE $Packet 0
    $rsize = Read-U16LE $Packet 2
    $now = Get-NowStamp
    $rtypeText = "0x{0:X4}" -f $rtype
    Write-Host "[$now] TCP reply port=$($Conn.Port) peer=$($Conn.Peer) type=$rtypeText size=$rsize" -ForegroundColor Magenta
}

function Send-LobbyChatBroadcast(
    [object]$Sender,
    [byte[]]$Packet
) {
    $strings = Get-NulTerminatedStrings (Get-PacketPayload $Packet) 1
    $msg = ""
    $account = $Sender.Account
    if ($strings.Count -ge 1) { $msg = $strings[0] }
    if ($strings.Count -ge 2) { $account = $strings[1] }

    $now = Get-NowStamp
    Write-Host "[$now] Lobby chat broadcast from=$account message=$msg" -ForegroundColor Green

    foreach ($target in $script:Clients.ToArray()) {
        if ($target.Port -ne $Sender.Port) { continue }
        if ($target.Peer -eq $Sender.Peer) { continue }
        if (-not $target.Client.Connected) { continue }
        if ([string]::IsNullOrWhiteSpace($target.Account)) { continue }
        try {
            $serverMsgPayload = New-ServerMessagePayload $msg $account
            Send-TcpPacket $target (New-TgPacket 0x13FF $serverMsgPayload) "tcp-broadcast"
        } catch {
            $errNow = Get-NowStamp
            Write-Host "[$errNow] Lobby chat broadcast failed peer=$($target.Peer) - $($_.Exception.Message)" -ForegroundColor Yellow
            try { $target.Stream.Close() } catch {}
            try { $target.Client.Close() } catch {}
            [void]$script:Clients.Remove($target)
        }
    }
}

function Send-RoomBroadcast(
    [object]$Sender,
    [byte[]]$Packet,
    [string]$Reason
) {
    $roomTitle = Resolve-ConnectionRoomTitle $Sender
    if ([string]::IsNullOrWhiteSpace($roomTitle)) {
        $now = Get-NowStamp
        $reqType = Read-U16LE $Packet 0
        $typeText = "0x{0:X4}" -f $reqType
        Write-ServerEvent "[$now] Room broadcast skipped no-room peer=$($Sender.Peer) account=$($Sender.Account) type=$typeText reason=$Reason" ([ConsoleColor]::DarkYellow)
        return
    }

    $now = Get-NowStamp
    $reqType = Read-U16LE $Packet 0
    $typeText = "0x{0:X4}" -f $reqType
    Write-ServerEvent "[$now] Room broadcast room=$roomTitle from=$($Sender.Account) type=$typeText reason=$Reason" ([ConsoleColor]::Green)

    $sentCount = 0
    foreach ($target in $script:Clients.ToArray()) {
        if ($target.Port -ne $Sender.Port) { continue }
        if ($target.Peer -eq $Sender.Peer) { continue }
        if (-not $target.Client.Connected) { continue }
        $targetRoomTitle = Resolve-ConnectionRoomTitle $target
        if ($targetRoomTitle -ne $roomTitle) { continue }
        try {
            Send-TcpPacket $target $Packet "tcp-room-broadcast"
            $sentCount++
        } catch {
            $errNow = Get-NowStamp
            Write-ServerEvent "[$errNow] Room broadcast failed peer=$($target.Peer) - $($_.Exception.Message)" ([ConsoleColor]::Yellow)
            try { $target.Stream.Close() } catch {}
            try { $target.Client.Close() } catch {}
            [void]$script:Clients.Remove($target)
        }
    }

    if ($sentCount -eq 0) {
        $known = @($script:Clients.ToArray() | Where-Object { $_.Port -eq $Sender.Port } | ForEach-Object { "$($_.Account)@$($_.Peer)/room=$($_.RoomTitle)" })
        $knownText = if ($known.Count -gt 0) { $known -join ", " } else { "(none)" }
        $now = Get-NowStamp
        Write-ServerEvent "[$now] Room broadcast no-target room=$roomTitle from=$($Sender.Account) type=$typeText reason=$Reason known=$knownText" ([ConsoleColor]::DarkYellow)
    } else {
        $now = Get-NowStamp
        Write-ServerEvent "[$now] Room broadcast delivered room=$roomTitle type=$typeText reason=$Reason targets=$sentCount" ([ConsoleColor]::DarkGreen)
    }

    return
}

function Send-RoomMemberListBroadcast(
    [object]$Sender,
    [object]$Room,
    [string]$Reason
) {
    if ($null -eq $Room) { return }
    if ([string]::IsNullOrWhiteSpace($Sender.RoomTitle)) { return }

    $packets = New-Object System.Collections.Generic.List[byte[]]
    Add-ChannelUserListReplies $packets $Room

    $now = Get-NowStamp
    Write-Host "[$now] Room member-list broadcast room=$($Sender.RoomTitle) from=$($Sender.Account) reason=$Reason count=$($packets.Count)" -ForegroundColor Green

    foreach ($target in $script:Clients.ToArray()) {
        if ($target.Port -ne $Sender.Port) { continue }
        if ($target.Peer -eq $Sender.Peer) { continue }
        if (-not $target.Client.Connected) { continue }
        if ($target.RoomTitle -ne $Sender.RoomTitle) { continue }
        try {
            foreach ($packet in $packets) {
                Send-TcpPacket $target $packet "tcp-room-members"
            }
        } catch {
            $errNow = Get-NowStamp
            Write-Host "[$errNow] Room member-list broadcast failed peer=$($target.Peer) - $($_.Exception.Message)" -ForegroundColor Yellow
            try { $target.Stream.Close() } catch {}
            try { $target.Client.Close() } catch {}
            [void]$script:Clients.Remove($target)
        }
    }
}

function Send-GameStartSync(
    [object]$Sender,
    [byte[]]$Packet
) {
    $now = Get-NowStamp
    $typeText = if ($Packet.Length -ge 2) { "0x{0:X4}" -f (Read-U16LE $Packet 0) } else { "n/a" }
    $payloadHex = if ($Packet.Length -gt 4) { (($Packet[4..($Packet.Length - 1)] | ForEach-Object { $_.ToString("X2") }) -join " ") } else { "" }
    Write-ServerEvent "[$now] Game start sync mode=$script:GameStartSyncMode peer=$($Sender.Peer) account=$($Sender.Account) room=$($Sender.RoomTitle) type=$typeText payload=$payloadHex" ([ConsoleColor]::Green)

    if ($script:GameStartSyncMode -eq "none") {
        Write-ServerEvent "[$now] Game start relay suppressed room=$($Sender.RoomTitle) from=$($Sender.Account)" ([ConsoleColor]::DarkYellow)
        return
    }

    if ($script:GameStartSyncMode -eq "original" -or $script:GameStartSyncMode -eq "original-plus-accept" -or $script:GameStartSyncMode -eq "original-plus-variants") {
        Send-RoomBroadcast $Sender $Packet "game-start-original"
    }

    if (($script:GameStartSyncMode -eq "accept-only" -or $script:GameStartSyncMode -eq "original-plus-accept" -or $script:GameStartSyncMode -eq "original-plus-variants") -and $Packet.Length -ge 7) {
        $acceptPacket = New-Object byte[] $Packet.Length
        [Array]::Copy($Packet, 0, $acceptPacket, 0, $Packet.Length)
        $acceptPacket[5] = 1
        Send-RoomBroadcast $Sender $acceptPacket "game-start-accept-variant"
    }

    if ($script:GameStartSyncMode -eq "original-plus-variants" -and $Packet.Length -ge 7) {
        $variants = @(
            @{ A = [byte]1; B = [byte]0; Name = "game-start-action1-status0" },
            @{ A = [byte]1; B = [byte]1; Name = "game-start-action1-status1" },
            @{ A = [byte]0; B = [byte]1; Name = "game-start-action0-status1" }
        )

        foreach ($variant in $variants) {
            $variantPacket = New-Object byte[] $Packet.Length
            [Array]::Copy($Packet, 0, $variantPacket, 0, $Packet.Length)
            $variantPacket[4] = $variant.A
            $variantPacket[5] = $variant.B
            Send-RoomBroadcast $Sender $variantPacket $variant.Name
        }
    }
}

function Add-UdpPeer([int]$Port, [Net.IPEndPoint]$Remote) {
    $key = "$Port|$($Remote.ToString())"
    if ($script:UdpPeerKeys.Contains($key)) { return }

    [void]$script:UdpPeerKeys.Add($key)
    $script:UdpPeers.Add([pscustomobject]@{
        Port = $Port
        EndPoint = [Net.IPEndPoint]::new($Remote.Address, $Remote.Port)
    })

    $now = Get-NowStamp
    Write-Host "[$now] UDP relay peer registered port=$Port peer=$($Remote.ToString())" -ForegroundColor Green
}

function Send-UdpRawRelay(
    [object]$Entry,
    [Net.IPEndPoint]$Remote,
    [byte[]]$Data
) {
    if (-not $script:EnableUdpRelay) { return }
    if ($Data.Length -le 0) { return }

    Add-UdpPeer $Entry.Port $Remote

    $sentCount = 0
    foreach ($peer in $script:UdpPeers.ToArray()) {
        if ($peer.Port -ne $Entry.Port) { continue }
        if ($peer.EndPoint.ToString() -eq $Remote.ToString()) { continue }

        try {
            [void]$Entry.Client.Send($Data, $Data.Length, $peer.EndPoint)
            $sentCount++
            Save-PacketLog "udp-relay" $Entry.Port $peer.EndPoint.ToString() $Data
        } catch {
            $now = Get-NowStamp
            Write-Host "[$now] UDP relay failed port=$($Entry.Port) peer=$($peer.EndPoint.ToString()) - $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }

    if ($sentCount -eq 0) {
        $warnKey = "$($Entry.Port)|$($Remote.ToString())"
        if ($script:UdpNoTargetWarned.Add($warnKey)) {
            $knownPeers = @(
                $script:UdpPeers.ToArray() |
                    Where-Object { $_.Port -eq $Entry.Port } |
                    ForEach-Object { $_.EndPoint.ToString() }
            )
            $now = Get-NowStamp
            $knownText = if ($knownPeers.Count -gt 0) { $knownPeers -join ", " } else { "(none)" }
            Write-Host "[$now] UDP relay has no target port=$($Entry.Port) from=$($Remote.ToString()) known=$knownText" -ForegroundColor DarkYellow
        }
    }
}

function Close-All {
    foreach ($c in $script:Clients.ToArray()) {
        try { $c.Stream.Close() } catch {}
        try { $c.Client.Close() } catch {}
    }
    foreach ($l in $script:TcpListeners) {
        try { $l.Listener.Stop() } catch {}
    }
    foreach ($u in $script:UdpClients) {
        try { $u.Client.Close() } catch {}
    }
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$script:ResolvedLogDir = (Resolve-Path -LiteralPath $LogDir).Path
$script:ResolvedTranscriptPath = $null
$script:ResolvedEventLogPath = $null
if (-not [string]::IsNullOrWhiteSpace($TranscriptPath)) {
    $transcriptFullPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($TranscriptPath)
    $transcriptDir = Split-Path -Parent $transcriptFullPath
    if (-not [string]::IsNullOrWhiteSpace($transcriptDir)) {
        New-Item -ItemType Directory -Force -Path $transcriptDir | Out-Null
    }
    $script:ResolvedTranscriptPath = $transcriptFullPath
    try {
        Start-Transcript -Path $script:ResolvedTranscriptPath -Append | Out-Null
    } catch {
        Write-Host "Transcript start failed: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}
if (-not [string]::IsNullOrWhiteSpace($EventLogPath)) {
    $eventLogFullPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($EventLogPath)
    $eventLogDir = Split-Path -Parent $eventLogFullPath
    if (-not [string]::IsNullOrWhiteSpace($eventLogDir)) {
        New-Item -ItemType Directory -Force -Path $eventLogDir | Out-Null
    }
    $script:ResolvedEventLogPath = $eventLogFullPath
    Add-Content -LiteralPath $script:ResolvedEventLogPath -Value "===== RhakMu dummy server start $(Get-NowStamp) =====" -Encoding UTF8
}
$ip = [Net.IPAddress]::Parse($Bind)

$script:TcpListeners = New-Object System.Collections.Generic.List[object]
$script:UdpClients = New-Object System.Collections.Generic.List[object]
$script:UdpPeers = New-Object System.Collections.Generic.List[object]
$script:UdpPeerKeys = New-Object 'System.Collections.Generic.HashSet[string]'
$script:UdpNoTargetWarned = New-Object 'System.Collections.Generic.HashSet[string]'
$script:Clients = New-Object System.Collections.Generic.List[object]
$script:Rooms = New-Object System.Collections.Generic.List[object]
$script:NextRoomId = 1
$script:LobbyListReplySent = New-Object 'System.Collections.Generic.HashSet[string]'
$script:Accounts = @{
    "test" = "test1234"
}
for ($i = 1; $i -le 10; $i++) {
    $script:Accounts["test$i"] = "1111"
}
$script:CurrentConnKey = ""
$script:CurrentAccount = ""
$script:CurrentHost = ""
$script:CurrentRoomTitle = ""
$script:CheckClientResult = $CheckClientResult
$script:CheckClientReplyType = $CheckClientReplyType
$script:AnnouncementReplyMode = $AnnouncementReplyMode
$script:TestAccount = $TestAccount
$script:TestPassword = $TestPassword
$script:LoginResult = $LoginResult
$script:LoginReplyType = $LoginReplyType
$script:ChannelJoinResult = $ChannelJoinResult
$script:ChannelJoinReplyType = $ChannelJoinReplyType
$script:GuildReplyMode = $GuildReplyMode
$script:RankListReplyMode = $RankListReplyMode
$script:RoomListReplyMode = $RoomListReplyMode
$script:RoomMakeResult = $RoomMakeResult
$script:SendRoomJoinAfterMake = [bool]$SendRoomJoinAfterMake
if ($RoomJoinHost -eq "127.0.0.1" -or $RoomJoinHost -eq "localhost") {
    $script:RoomJoinHost = Get-PreferredRoomJoinHost
} else {
    $script:RoomJoinHost = $RoomJoinHost
}
$script:RoomHostOverrideMap = @{}
foreach ($entryGroup in @($RoomHostOverrides)) {
    if ([string]::IsNullOrWhiteSpace($entryGroup)) { continue }
    foreach ($entry in ($entryGroup -split ",")) {
        $entry = $entry.Trim()
        if ([string]::IsNullOrWhiteSpace($entry)) { continue }
        $parts = $entry.Split("=", 2, [StringSplitOptions]::None)
        if ($parts.Count -ne 2 -or [string]::IsNullOrWhiteSpace($parts[0]) -or [string]::IsNullOrWhiteSpace($parts[1])) {
            Write-ServerEvent "[$(Get-NowStamp)] Ignoring invalid RoomHostOverrides entry: $entry" ([ConsoleColor]::Yellow)
            continue
        }
        $accountOverride = $parts[0].Trim()
        $hostOverride = $parts[1].Trim()
        if ($hostOverride -match "[=,]") {
            Write-ServerEvent "[$(Get-NowStamp)] Ignoring invalid RoomHostOverrides host for $accountOverride`: $hostOverride" ([ConsoleColor]::Yellow)
            continue
        }
        $script:RoomHostOverrideMap[$accountOverride] = $hostOverride
    }
}
$script:ChannelUserListReplyMode = $ChannelUserListReplyMode
$script:EnableUdpRelay = $EnableUdpRelay
$script:GameStartSyncMode = $GameStartSyncMode
$script:AcceptLikelyAccountPackets = [bool]$AcceptLikelyAccountPackets

Write-Host "RhakMu dummy server" -ForegroundColor Green
Write-Host "Bind: $Bind"
Write-Host "Ports: $($Ports -join ', ')"
Write-Host "AutoReply: $AutoReply"
Write-Host "CheckClientResult: $CheckClientResult"
Write-Host "CheckClientReplyType: $CheckClientReplyType"
Write-Host "AnnouncementReplyMode: $AnnouncementReplyMode"
Write-Host "TestAccount: $TestAccount"
Write-Host "TestPassword: $TestPassword"
Write-Host "Accounts: $($script:Accounts.Keys -join ', ')"
Write-Host "LoginResult: $LoginResult"
Write-Host "LoginReplyType: $LoginReplyType"
Write-Host "ChannelJoinResult: $ChannelJoinResult"
Write-Host "ChannelJoinReplyType: $ChannelJoinReplyType"
Write-Host "GuildReplyMode: $GuildReplyMode"
Write-Host "RankListReplyMode: $RankListReplyMode"
Write-Host "RoomListReplyMode: $RoomListReplyMode"
Write-Host "RoomMakeResult: $RoomMakeResult"
Write-Host "SendRoomJoinAfterMake: $([bool]$SendRoomJoinAfterMake)"
Write-Host "RoomJoinHost: $script:RoomJoinHost"
Write-Host "RoomHostOverrides: $(if ($script:RoomHostOverrideMap.Count -gt 0) { (($script:RoomHostOverrideMap.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join ', ') } else { '(none)' })"
Write-Host "SkipUdpPorts: $($SkipUdpPorts -join ',')"
Write-Host "EnableUdpRelay: $([bool]$EnableUdpRelay)"
Write-Host "GameStartSyncMode: $GameStartSyncMode"
Write-Host "ChannelUserListReplyMode: $ChannelUserListReplyMode"
Write-Host "AcceptLikelyAccountPackets: $([bool]$AcceptLikelyAccountPackets)"
Write-Host "LogDir: $script:ResolvedLogDir"
if ($script:ResolvedTranscriptPath) { Write-Host "TranscriptPath: $script:ResolvedTranscriptPath" }
if ($script:ResolvedEventLogPath) { Write-Host "EventLogPath: $script:ResolvedEventLogPath" }
Write-Host "Press Ctrl+C to stop."
Write-Host ""

foreach ($port in ($Ports | Sort-Object -Unique)) {
    try {
        $listener = [Net.Sockets.TcpListener]::new($ip, $port)
        $listener.Server.SetSocketOption([Net.Sockets.SocketOptionLevel]::Socket, [Net.Sockets.SocketOptionName]::ReuseAddress, $true)
        $listener.Start()
        $script:TcpListeners.Add([pscustomobject]@{ Port = $port; Listener = $listener })
        Write-Host "TCP listening $Bind`:$port" -ForegroundColor DarkGreen
    } catch {
        Write-Host "TCP bind failed $Bind`:$port - $($_.Exception.Message)" -ForegroundColor Yellow
    }

    if ($SkipUdpPorts -contains $port) {
        Write-Host "UDP skipped $Bind`:$port" -ForegroundColor DarkYellow
    } else {
        try {
            $udp = [Net.Sockets.UdpClient]::new()
            $udp.Client.SetSocketOption([Net.Sockets.SocketOptionLevel]::Socket, [Net.Sockets.SocketOptionName]::ReuseAddress, $true)
            $udp.Client.Bind([Net.IPEndPoint]::new($ip, $port))
            $script:UdpClients.Add([pscustomobject]@{ Port = $port; Client = $udp })
            Write-Host "UDP listening $Bind`:$port" -ForegroundColor DarkGreen
        } catch {
            Write-Host "UDP bind failed $Bind`:$port - $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
}

try {
    $buffer = New-Object byte[] 8192
    while ($true) {
        foreach ($entry in $script:TcpListeners.ToArray()) {
            while ($entry.Listener.Pending()) {
                $client = $entry.Listener.AcceptTcpClient()
                $client.NoDelay = $true
                $stream = $client.GetStream()
                $peer = $client.Client.RemoteEndPoint.ToString()
                $script:Clients.Add([pscustomobject]@{
                    Port = $entry.Port
                    Client = $client
                    Stream = $stream
                    Peer = $peer
                    Account = ""
                    RoomTitle = ""
                    Buffer = (New-Object System.Collections.Generic.List[byte])
                })
                $now = Get-NowStamp
                Write-Host "[$now] TCP connected port=$($entry.Port) peer=$peer" -ForegroundColor Green
            }
        }

        foreach ($conn in $script:Clients.ToArray()) {
            try {
                if (-not $conn.Client.Connected) {
                    $script:Clients.Remove($conn) | Out-Null
                    continue
                }
                while ($conn.Stream.DataAvailable) {
                    $read = $conn.Stream.Read($buffer, 0, $buffer.Length)
                    if ($read -le 0) { break }
                    $data = New-Object byte[] $read
                    [Array]::Copy($buffer, 0, $data, 0, $read)

                    $conn.Buffer.AddRange($data)
                    $streamParts = Split-TgStream $conn.Buffer.ToArray()
                    $conn.Buffer.Clear()
                    $conn.Buffer.AddRange($streamParts.Remaining)

                    foreach ($packet in $streamParts.Packets) {
                        Save-PacketLog "tcp" $conn.Port $conn.Peer $packet
                        if (Test-HttpRequest $packet) {
                            $reply = New-HttpReply $packet
                            $conn.Stream.Write($reply, 0, $reply.Length)
                            $now = Get-NowStamp
                            Write-Host "[$now] HTTP reply port=$($conn.Port) peer=$($conn.Peer) bytes=$($reply.Length)" -ForegroundColor Magenta
                            try { $conn.Stream.Close() } catch {}
                            try { $conn.Client.Close() } catch {}
                            $script:Clients.Remove($conn) | Out-Null
                            break
                        }
                        if ($packet.Length -ge 4) {
                            $reqType = Read-U16LE $packet 0
                            $script:CurrentConnKey = Get-ConnectionKey $conn.Port $conn.Peer
                            $script:CurrentAccount = $conn.Account
                            $script:CurrentHost = Get-PeerHost $conn.Peer
                            $script:CurrentRoomTitle = $conn.RoomTitle
                            $replySet = New-RhakMuProtocolReplies $packet
                            if ($replySet.Count -eq 0 -and -not (Test-SkipAutoReply $reqType)) {
                                $replySet = New-ReplyPackets $reqType $AutoReply
                            }

                            if ($reqType -eq 0x05FF) {
                                $login = Get-LoginFields $packet
                                if ((Test-RhakMuLogin $packet) -eq 0) {
                                    $conn.Account = $login.Account
                                    Remove-StaleConnectionsForAccount $conn.Account $conn
                                    $oldAccount = $script:CurrentAccount
                                    $script:CurrentAccount = $conn.Account
                                    [void](Remove-RoomsForCurrentClient)
                                    $script:CurrentAccount = $oldAccount
                                    $now = Get-NowStamp
                                    Write-Host "[$now] Login accepted peer=$($conn.Peer) account=$($conn.Account)" -ForegroundColor Green
                                } else {
                                    $now = Get-NowStamp
                                    Write-Host "[$now] Login rejected peer=$($conn.Peer) account=$($login.Account)" -ForegroundColor Yellow
                                }
                            }

                            if ($reqType -eq 0x0EFF) {
                                $createStrings = Get-AsciiStrings (Get-PacketPayload $packet) 2
                                if ($createStrings.Count -ge 1) {
                                    $conn.RoomTitle = $createStrings[0]
                                    $now = Get-NowStamp
                                    Write-Host "[$now] Client room owner set peer=$($conn.Peer) account=$($conn.Account) room=$($conn.RoomTitle)" -ForegroundColor Green
                                }
                            }

                            if ($reqType -eq 0x10FF) {
                                if (Test-PostGameRoomReentryPacket $packet) {
                                    $now = Get-NowStamp
                                    Write-Host "[$now] Client post-game room reentry ignored peer=$($conn.Peer) account=$($conn.Account) room=$($conn.RoomTitle)" -ForegroundColor DarkYellow
                                } else {
                                    $room = Find-RoomForJoin $packet
                                    if ($null -ne $room) {
                                        $conn.RoomTitle = $room.Title
                                        Add-RoomMember $room $conn.Account (Resolve-RoomHost (Get-PeerHost $conn.Peer))
                                        $now = Get-NowStamp
                                        Write-Host "[$now] Client room joined peer=$($conn.Peer) account=$($conn.Account) room=$($conn.RoomTitle) hostAccount=$($room.Owner) host=$($room.Host)" -ForegroundColor Green
                                        Send-RoomMemberListBroadcast $conn $room "room-join"
                                    }
                                }
                            }

                            foreach ($reply in $replySet) {
                                Send-TcpPacket $conn $reply "tcp-reply"
                            }

                            if ($reqType -eq 0x12FF) {
                                Send-LobbyChatBroadcast $conn $packet
                            }

                            if ($reqType -eq 0x0FFF) {
                                Send-GameStartSync $conn $packet
                            }

                            if ($reqType -eq 0x24FF -or $reqType -eq 0x27FF) {
                                Send-RoomBroadcast $conn $packet "game-cleanup"
                            }

                            if ($reqType -eq 0xFEFE) {
                                [void](Remove-RoomsForCurrentClient)
                                $now = Get-NowStamp
                                Write-Host "[$now] Crash report received peer=$($conn.Peer) account=$($conn.Account); cleaned stale room state" -ForegroundColor DarkYellow
                            }

                            if ($reqType -eq 0x11FF) {
                                $room = Find-RoomByTitle $conn.RoomTitle
                                if ($null -ne $room) {
                                    Remove-RoomMember $room $conn.Account
                                }
                                $conn.RoomTitle = ""
                            }
                        }
                    }
                }
            } catch {
                $now = Get-NowStamp
                Write-Host "[$now] TCP closed/error port=$($conn.Port) peer=$($conn.Peer) - $($_.Exception.Message)" -ForegroundColor Yellow
                try { $conn.Stream.Close() } catch {}
                try { $conn.Client.Close() } catch {}
                $script:Clients.Remove($conn) | Out-Null
            }
        }

        foreach ($entry in $script:UdpClients.ToArray()) {
            try {
                while ($entry.Client.Available -gt 0) {
                    $remote = [Net.IPEndPoint]::new([Net.IPAddress]::Any, 0)
                    $data = $entry.Client.Receive([ref]$remote)
                    Add-UdpPeer $entry.Port $remote
                    $sentUdpReply = $false
                    $packets = Split-TgPackets $data
                    foreach ($packet in $packets) {
                        Save-PacketLog "udp" $entry.Port $remote.ToString() $packet
                        if ($packet.Length -ge 4) {
                            $reqType = Read-U16LE $packet 0
                            $script:CurrentConnKey = Get-ConnectionKey $entry.Port $remote.ToString()
                            $replySet = New-RhakMuProtocolReplies $packet
                            if ($replySet.Count -eq 0 -and -not (Test-SkipAutoReply $reqType)) {
                                $replySet = New-ReplyPackets $reqType $AutoReply
                            }

                            foreach ($reply in $replySet) {
                                [void]$entry.Client.Send($reply, $reply.Length, $remote)
                                $sentUdpReply = $true
                                Save-PacketLog "udp-reply" $entry.Port $remote.ToString() $reply
                                $rtype = Read-U16LE $reply 0
                                $rsize = Read-U16LE $reply 2
                                $now = Get-NowStamp
                                $rtypeText = "0x{0:X4}" -f $rtype
                                $remoteText = $remote.ToString()
                                Write-Host "[$now] UDP reply port=$($entry.Port) peer=$remoteText type=$rtypeText size=$rsize" -ForegroundColor Magenta
                            }
                        }
                    }
                    if (-not $sentUdpReply) {
                        Send-UdpRawRelay $entry $remote $data
                    }
                }
            } catch {
                $now = Get-NowStamp
                Write-Host "[$now] UDP error port=$($entry.Port) - $($_.Exception.Message)" -ForegroundColor Yellow
            }
        }

        Start-Sleep -Milliseconds $TickMs
    }
} finally {
    Close-All
    Write-Host "Stopped."
    try {
        if ($script:ResolvedTranscriptPath) { Stop-Transcript | Out-Null }
    } catch {}
}
