# RhakMu Map Editor local helper (Windows PowerShell 5.1+)
# Serves the editor on http://127.0.0.1:47231/ and lets it list/open/save maps in ..\Data\Maps
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$game = Split-Path -Parent $root
$maps = Join-Path $game 'Data\Maps'
$port = 47231
$utf8 = New-Object System.Text.UTF8Encoding($false)

$listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, $port)
try { $listener.Start() } catch {
  # already running: just open the browser
  Start-Process ("http://127.0.0.1:{0}/RhakMuMapEditor.html" -f $port); exit
}
Write-Host "RhakMu Map Editor helper running: http://127.0.0.1:$port/  (close this window to stop)"
Write-Host "Maps folder: $maps"
Start-Process ("http://127.0.0.1:{0}/RhakMuMapEditor.html" -f $port)

function Send($stream, [int]$code, [string]$type, [byte[]]$body) {
  $reason = @{200='OK';204='No Content';400='Bad Request';403='Forbidden';404='Not Found';500='Internal Server Error'}[$code]
  $head = "HTTP/1.1 $code $reason`r`nContent-Type: $type`r`nContent-Length: $($body.Length)`r`nCache-Control: no-store`r`nConnection: close`r`n`r`n"
  $hb = [System.Text.Encoding]::ASCII.GetBytes($head)
  $stream.Write($hb, 0, $hb.Length)
  if ($body.Length -gt 0) { $stream.Write($body, 0, $body.Length) }
  $stream.Flush()
}
function SendText($stream, [int]$code, [string]$text, [string]$type = 'text/plain; charset=utf-8') { Send $stream $code $type ($utf8.GetBytes($text)) }
function JsonStr([string]$s) { return '"' + ($s -replace '\\', '\\' -replace '"', '\"') + '"' }

# map name -> safe full path inside Data\Maps (relative path like "[2]Name.rkm" or "Download\[2]Name.rkm")
function MapPath([string]$rel) {
  if ([string]::IsNullOrWhiteSpace($rel)) { return $null }
  $rel = $rel -replace '/', '\'
  if ($rel -match '\.\.' -or $rel -match ':' -or $rel.StartsWith('\')) { return $null }
  if (-not $rel.ToLower().EndsWith('.rkm')) { return $null }
  return Join-Path $maps $rel
}

$mime = @{ '.html'='text/html; charset=utf-8'; '.js'='application/javascript; charset=utf-8'; '.txt'='text/plain; charset=utf-8'; '.png'='image/png' }

while ($true) {
  $client = $listener.AcceptTcpClient()
  try {
    $client.ReceiveTimeout = 15000
    $stream = $client.GetStream()
    # read request head
    $buf = New-Object byte[] 65536; $ms = New-Object System.IO.MemoryStream; $headEnd = -1
    while ($headEnd -lt 0) {
      $n = $stream.Read($buf, 0, $buf.Length); if ($n -le 0) { break }
      $ms.Write($buf, 0, $n); $all = $ms.ToArray()
      for ($i = 3; $i -lt $all.Length; $i++) { if ($all[$i-3] -eq 13 -and $all[$i-2] -eq 10 -and $all[$i-1] -eq 13 -and $all[$i] -eq 10) { $headEnd = $i + 1; break } }
      if ($ms.Length -gt 1048576) { break }
    }
    if ($headEnd -lt 0) { $client.Close(); continue }
    $all = $ms.ToArray()
    $head = [System.Text.Encoding]::ASCII.GetString($all, 0, $headEnd)
    $lines = $head -split "`r`n"
    $parts = $lines[0] -split ' '
    $method = $parts[0]; $target = $parts[1]
    $len = 0
    foreach ($l in $lines) { if ($l -match '^(?i)content-length:\s*(\d+)') { $len = [int]$matches[1] } }
    $body = New-Object byte[] $len
    $have = $all.Length - $headEnd
    if ($have -gt 0) { [Array]::Copy($all, $headEnd, $body, 0, [Math]::Min($have, $len)) }
    while ($have -lt $len) { $n = $stream.Read($body, $have, $len - $have); if ($n -le 0) { break }; $have += $n }

    $q = ''; $path = $target
    if ($target.Contains('?')) { $path = $target.Substring(0, $target.IndexOf('?')); $q = $target.Substring($target.IndexOf('?') + 1) }
    $path = [Uri]::UnescapeDataString($path)
    $name = $null
    foreach ($kv in ($q -split '&')) { if ($kv.StartsWith('name=')) { $name = [Uri]::UnescapeDataString($kv.Substring(5).Replace('+', ' ')) } }

    if ($path -eq '/api/ping') { SendText $stream 200 '{"ok":true}' 'application/json' }
    elseif ($path -eq '/api/maps') {
      $items = @()
      if (Test-Path -LiteralPath $maps) {
        foreach ($f in (Get-ChildItem -LiteralPath $maps -Recurse -File | Where-Object { $_.Extension -ieq '.rkm' })) {
          $rel = $f.FullName.Substring($maps.Length).TrimStart('\')
          $items += ('{"name":' + (JsonStr $rel) + ',"size":' + $f.Length + ',"mtime":' + [long]($f.LastWriteTimeUtc - [datetime]'1970-01-01').TotalMilliseconds + '}')
        }
      }
      SendText $stream 200 ('{"folder":' + (JsonStr $maps) + ',"maps":[' + ($items -join ',') + ']}') 'application/json; charset=utf-8'
    }
    elseif ($path -eq '/api/map') {
      $full = MapPath $name
      if (-not $full) { SendText $stream 400 'bad name' }
      elseif ($method -eq 'GET') {
        if (Test-Path -LiteralPath $full) { Send $stream 200 'application/octet-stream' ([System.IO.File]::ReadAllBytes($full)) } else { SendText $stream 404 'not found' }
      }
      elseif ($method -eq 'PUT' -or $method -eq 'POST') {
        if ($body.Length -lt 76 -or $body[0] -ne 0x4a -or $body[1] -ne 0x32 -or $body[2] -ne 0x4d) { SendText $stream 400 'not a J2M map' }
        else {
          $dir = Split-Path -Parent $full
          if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
          if (Test-Path -LiteralPath $full) { Copy-Item -LiteralPath $full -Destination ($full + '.bak') -Force }
          [System.IO.File]::WriteAllBytes($full, $body)
          SendText $stream 200 ('{"ok":true,"path":' + (JsonStr $full) + '}') 'application/json; charset=utf-8'
        }
      }
      else { SendText $stream 400 'method' }
    }
    else {
      if ($path -eq '/') { $path = '/RhakMuMapEditor.html' }
      $rel = $path.TrimStart('/') -replace '/', '\'
      $full = Join-Path $root $rel
      if ($rel -match '\.\.' -or -not (Test-Path -LiteralPath $full -PathType Leaf)) { SendText $stream 404 'not found' }
      else {
        $ext = [System.IO.Path]::GetExtension($full).ToLower(); $t = $mime[$ext]; if (-not $t) { $t = 'application/octet-stream' }
        Send $stream 200 $t ([System.IO.File]::ReadAllBytes($full))
      }
    }
  } catch {
    try { SendText $stream 500 ($_.Exception.Message) } catch {}
    Write-Host ("error: " + $_.Exception.Message)
  } finally { $client.Close() }
}
