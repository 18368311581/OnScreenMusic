param(
    [string]$SourceRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$Destination = (Join-Path (Split-Path -Parent $PSScriptRoot) 'release-v1.0')
)
$ErrorActionPreference = 'Stop'
$sourceDirectory = [IO.Path]::GetFullPath($SourceRoot)
$targetDirectory = [IO.Path]::GetFullPath($Destination)
if ($sourceDirectory.TrimEnd('\') -eq $targetDirectory.TrimEnd('\')) {
    throw 'Source and destination must differ.'
}
$files = @(
    'MusicWorkshop.pyw', 'MusicWorkshop.vbs', 'requirements-workshop.txt', 'VERSION',
    'workshop/__init__.py', 'workshop/core.py', 'workshop/gui.py', 'workshop/audio.py',
    'workshop/runner.py', 'workshop/worker.py',
    'workshop/shared_settings.py', 'workshop/theme.py', 'workshop/qt_ui.py', 'workshop/playlists.py',
    'workshop/tool_setup.py', 'workshop/help_page.py',
    'workshop/maintenance.py', 'workshop/runtime.py', 'workshop/version.py',
    'tools/benchmark_workshop_startup.py',
    'workshop/icons/check.svg', 'workshop/icons/down.svg', 'workshop/icons/up.svg',
    'workshop/icons/workshop.svg',
    'tools/ai_lyrics.py', 'tools/prepare_music.py',
    'tools/generate_lrc.py', 'tools/convert_dpl_playlist.py'
)
foreach ($relative in $files) {
    if (-not (Test-Path -LiteralPath (Join-Path $sourceDirectory $relative) -PathType Leaf)) {
        throw "Missing source: $relative"
    }
}
foreach ($relative in $files) {
    $source = Join-Path $sourceDirectory $relative
    $target = [IO.Path]::GetFullPath((Join-Path $targetDirectory $relative))
    if (-not $target.StartsWith($targetDirectory.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Destination escaped the selected directory.'
    }
    New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $target -Force
}
Write-Output "Music Workshop source files deployed to $targetDirectory"
Write-Output 'Models, Whisper binaries, FFmpeg, credentials and media were not copied.'
