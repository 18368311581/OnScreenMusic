param(
    [string]$PythonExe = (Join-Path (Split-Path -Parent $PSScriptRoot) '.packaging-venv/Scripts/python.exe'),
    [string]$PlayerExe = (Join-Path (Split-Path -Parent $PSScriptRoot) 'build-release/OnScreenMusic.exe'),
    [string]$QtDirectory = 'D:/Qt/Qt5.14.0/5.14.0/mingw73_64',
    [string]$MinGWDirectory = 'D:/Qt/Qt5.14.0/Tools/mingw730_64',
    [string]$OutputDirectory = (Join-Path (Split-Path -Parent $PSScriptRoot) 'packages')
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) { throw 'Packaging Python was not found.' }
& $PythonExe -m PyInstaller --noconfirm --distpath (Join-Path $projectRoot 'dist-workshop') --workpath (Join-Path $projectRoot 'build-workshop') (Join-Path $PSScriptRoot 'MusicWorkshop.spec')
if ($LASTEXITCODE -ne 0) { throw 'Music Workshop packaging failed.' }
$version = [IO.File]::ReadAllText((Join-Path $projectRoot 'VERSION')).Trim()
$destination = Join-Path ([IO.Path]::GetFullPath($OutputDirectory)) ("OnScreenMusic-$version-windows-x64")
if (Test-Path -LiteralPath $destination) { throw 'Output directory already exists.' }
New-Item -ItemType Directory -Path $destination | Out-Null
Get-ChildItem -LiteralPath (Join-Path $projectRoot 'dist-workshop/MusicWorkshop') | Copy-Item -Destination $destination -Recurse
Copy-Item -LiteralPath $PlayerExe -Destination (Join-Path $destination 'OnScreenMusic.exe')
foreach ($file in @('Qt5Core.dll','Qt5Gui.dll','Qt5Multimedia.dll','Qt5Network.dll','Qt5Widgets.dll')) {
    Copy-Item -LiteralPath (Join-Path $QtDirectory "bin/$file") -Destination (Join-Path $destination $file)
}
foreach ($file in @('libgcc_s_seh-1.dll','libstdc++-6.dll','libwinpthread-1.dll')) {
    Copy-Item -LiteralPath (Join-Path $MinGWDirectory "bin/$file") -Destination (Join-Path $destination $file)
}
foreach ($relative in @('platforms/qwindows.dll','audio/qtaudio_windows.dll','bearer/qgenericbearer.dll','mediaservice/dsengine.dll','mediaservice/qtmedia_audioengine.dll')) {
    $target = Join-Path $destination $relative
    New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $QtDirectory "plugins/$relative") -Destination $target
}
foreach ($folder in @('music','lyrics','playlists')) { New-Item -ItemType Directory -Path (Join-Path $destination $folder) | Out-Null }
Copy-Item -LiteralPath (Join-Path $projectRoot 'README.md') -Destination (Join-Path $destination 'README.md')
foreach ($file in @('VERSION','LICENSE','CHANGELOG.md')) { Copy-Item -LiteralPath (Join-Path $projectRoot $file) -Destination (Join-Path $destination $file) }
Copy-Item -LiteralPath (Join-Path $projectRoot 'docs') -Destination (Join-Path $destination 'docs') -Recurse
$notice = @'
On Screen Music

双击 MusicWorkshop.exe 打开音乐管理，双击 OnScreenMusic.exe 打开桌面播放器。
不需要另装 Python。两个 EXE、MusicWorkshopTool.exe 及运行目录请保持完整。

music 放 MP3，lyrics 放同名 LRC，playlists 放 TXT 歌单。
首次使用时可在参数设置中下载或选择 FFmpeg、识别程序与模型；模型约 3.1 GB。
整项识别/校对成功后会自动更新对应歌词，旧歌词另存备份。
新素材转换出的 MP3 仍在工作目录，整理后再放入 music。

此更新包含附属的音乐管理工具 MusicWorkshop，采用整套软件统一版本。
尚未在其他电脑上完成验收，完整使用说明见 README.md 和 docs/USER_GUIDE.md。
本包不含个人配置、密钥、歌曲、歌词、模型或任务记录。
'@
[IO.File]::WriteAllText((Join-Path $destination '开始使用.txt'), $notice, [Text.UTF8Encoding]::new($false))
& $PythonExe -B (Join-Path $PSScriptRoot 'collect_workshop_notices.py') $destination --qt-directory $QtDirectory --mingw-directory $MinGWDirectory
if ($LASTEXITCODE -ne 0) { throw 'Collecting third-party notices failed.' }
Write-Output "On Screen Music release directory: $destination"
