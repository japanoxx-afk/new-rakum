# Builds nas-server\upload\rakmu\ : exactly the files to upload to File Station game-servers/rakmu/.
# server.py is copied from the repository root so the NAS runs the same server as the launcher.
# The upload folder never contains data/ - uploading it can never overwrite game records on the NAS.
# Usage (PowerShell, repository root or anywhere):  .\nas-server\Prepare-NasUpload.ps1
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent $here
$out = Join-Path $here 'upload\rakmu'

if (Test-Path $out) { Remove-Item -Recurse -Force $out }
New-Item -ItemType Directory -Force (Join-Path $out 'app') | Out-Null

Copy-Item (Join-Path $repo 'server.py') (Join-Path $out 'app\server.py')
Copy-Item (Join-Path $here 'app\nas_entry.py') (Join-Path $out 'app\nas_entry.py')
foreach ($f in 'compose.yaml', 'ports.txt', 'README.txt', 'HANDOFF.txt') {
    Copy-Item (Join-Path $here $f) (Join-Path $out $f)
}

$version = (Select-String -Path (Join-Path $out 'app\server.py') -Pattern '^SERVER_VERSION\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
$commit = (git -C $repo rev-parse --short HEAD) 2>$null
Set-Content -Path (Join-Path $out 'app\DEPLOYED_VERSION.txt') -Encoding ascii -Value @(
    "server_version=$version",
    "git_commit=$commit",
    "prepared=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
)

Write-Host "Upload folder ready: $out" -ForegroundColor Green
Write-Host "server.py version $version (commit $commit)"
Get-ChildItem -Recurse $out | Where-Object { -not $_.PSIsContainer } |
    ForEach-Object { '  ' + $_.FullName.Substring($out.Length + 1) + "  ($($_.Length) bytes)" }
