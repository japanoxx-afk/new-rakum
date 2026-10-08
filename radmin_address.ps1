# Only TGNet_Get_MyIPaddress in the verified TG_Net.dll build is replaced.
# Position-independent x86, cdecl; no Winsock, routing or checksum changes.
$script:addressOriginal = [Convert]::FromBase64String('gewAAQAAjUQkAGgAAQAAUOg/qAAAg/j/dQkywIHEAAEAAMOLjCQIAQAAi5QkBAEAAFGNRCQEUlDoM////4PEDIHEAAEAAMOQkJCQkJCQkJA=')
function New-RadminAddressCode([string]$IPAddress) {
    $ip = [Net.IPAddress]::Parse($IPAddress)
    if ($ip.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork -or $ip.GetAddressBytes()[0] -ne 26) { throw 'Expected a Radmin IPv4 address.' }
    $data = New-Object byte[] 16
    [Text.Encoding]::ASCII.GetBytes($ip.ToString()).CopyTo($data, 0)
    $code = [Collections.Generic.List[byte]]::new()
    # edx=buffer; reject NULL and capacity<16. Both jumps target xor eax,eax.
    $code.AddRange([byte[]](0x8b,0x54,0x24,0x04,0x85,0xd2,0x74,0x2b,0x0f,0xb7,0x4c,0x24,0x08,0x83,0xf9,0x10,0x72,0x21))
    for ($n=0; $n -lt 4; $n++) {
        if ($n -eq 0) { $code.AddRange([byte[]](0xc7,0x02)) }
        else { $code.AddRange([byte[]](0xc7,0x42,($n*4))) }
        $code.AddRange([byte[]]$data[($n*4)..($n*4+3)])
    }
    $code.AddRange([byte[]](0xb8,1,0,0,0,0xc3,0x31,0xc0,0xc3))
    while ($code.Count -lt 80) { $code.Add(0x90) }
    return ,$code.ToArray()
}
function Set-RadminDllBytes($Path, [byte[]]$Expected, [byte[]]$Replacement) {
    $bytes = [IO.File]::ReadAllBytes($Path)
    if ($bytes.Length -ne 81979 -or [Convert]::ToBase64String($bytes[0x2010..0x205f]) -ne [Convert]::ToBase64String($Expected)) { throw 'TG_Net.dll signature mismatch; no changes made.' }
    $Replacement.CopyTo($bytes, 0x2010)
    $temp = $Path + '.radmin-' + [guid]::NewGuid() + '.tmp'
    try {
        [IO.File]::WriteAllBytes($temp, $bytes)
        # Windows PowerShell 5 converts $null into an invalid empty path here.
        [IO.File]::Replace($temp, $Path, ($temp + '.previous'))
        Remove-Item -LiteralPath ($temp + '.previous')
    } finally { if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp } }
}
function Enable-RadminAddress($GameDir, $StateDir, $IPAddress) {
    $path = Join-Path $GameDir 'TG_Net.dll'
    $stateFile = Join-Path $StateDir 'address.json'
    if (Test-Path -LiteralPath $stateFile) { throw 'Previous address patch remains; restore it first.' }
    $code = New-RadminAddressCode $IPAddress
    $bytes = [IO.File]::ReadAllBytes($path)
    if ($bytes.Length -ne 81979 -or [Convert]::ToBase64String($bytes[0x2010..0x205f]) -ne [Convert]::ToBase64String($script:addressOriginal)) { throw 'Unsupported TG_Net.dll; no address patch applied.' }
    $backup = Join-Path $StateDir ('TG_Net-' + [guid]::NewGuid() + '.bak')
    [IO.File]::WriteAllBytes($backup, $bytes)
    @{Path=[IO.Path]::GetFullPath($path); IP=$IPAddress; Backup=$backup; Code=[Convert]::ToBase64String($code)} | ConvertTo-Json | Set-Content -LiteralPath $stateFile -Encoding UTF8
    Set-RadminDllBytes $path $script:addressOriginal $code
}
function Restore-RadminAddress($StateDir) {
    $stateFile = Join-Path $StateDir 'address.json'
    if (-not (Test-Path -LiteralPath $stateFile)) { return }
    $saved = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
    $bytes = [IO.File]::ReadAllBytes($saved.Path)
    if ($bytes.Length -ne 81979) { throw 'Cannot restore: DLL size changed.' }
    if ([Convert]::ToBase64String($bytes[0x2010..0x205f]) -ne [Convert]::ToBase64String($script:addressOriginal)) {
        Set-RadminDllBytes $saved.Path ([Convert]::FromBase64String($saved.Code)) $script:addressOriginal
    }
    Remove-Item -LiteralPath $stateFile
}
