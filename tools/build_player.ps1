param(
    [ValidateSet('Release','Debug')][string]$Configuration = 'Release',
    [string]$QtDirectory = 'D:/Qt/Qt5.14.0/5.14.0/mingw73_64',
    [string]$MinGWDirectory = 'D:/Qt/Qt5.14.0/Tools/mingw730_64',
    [string]$BuildDirectory = ''
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (-not $BuildDirectory) { $BuildDirectory = Join-Path $root ('build-' + $Configuration.ToLowerInvariant()) }
$qmake = Join-Path $QtDirectory 'bin/qmake.exe'
$make = Join-Path $MinGWDirectory 'bin/mingw32-make.exe'
foreach ($file in @($qmake,$make)) { if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Build tool missing: $file" } }
$previousPath = $env:PATH
try {
    $env:PATH = (Join-Path $MinGWDirectory 'bin') + ';' + (Join-Path $QtDirectory 'bin') + ';' + $env:PATH
    New-Item -ItemType Directory -Path $BuildDirectory -Force | Out-Null
    Push-Location $BuildDirectory
    try {
        $kind = $Configuration.ToLowerInvariant()
        $other = if ($kind -eq 'release') { 'debug' } else { 'release' }
        & $qmake (Join-Path $root 'on_screen_music.pro') "CONFIG+=$kind" "CONFIG-=$other"
        if ($LASTEXITCODE -ne 0) { throw 'qmake failed.' }
        & $make -j8
        if ($LASTEXITCODE -ne 0) { throw 'Player build failed.' }
    } finally { Pop-Location }
} finally { $env:PATH = $previousPath }
