# On Screen Music

这是一个 Windows 本地桌面歌词播放器项目。桌面播放器核心功能已完成并定为 v1.0，后续以修复真实问题为主；歌词生成、歌词优化、歌单整理和音频预处理等附属工具仍可继续开发。

`README.md` 面向实际使用和构建，记录命令、目录和操作方法；`AGENTS.md` 面向后续开发协作，记录技术约束、职责边界和验证要求，两者用途不同。

应用图标源文件位于 `assets/app_icon.png`，Windows 多尺寸图标位于 `assets/app_icon.ico`；构建时会嵌入 EXE，并用于应用窗口和系统托盘。

## 环境

- Windows 11。
- Python 3.12，不需要安装第三方 Python 包。
- 本机 FFmpeg 7.1.1，并包含 `loudnorm` 和 `libmp3lame`。
- Qt 5.14、Qt Creator、MinGW 7.3 64 位 Kit。

项目不会打包 FFmpeg。工具会依次查找：

1. `--ffmpeg` 指定的文件。
2. PATH 中的 `ffmpeg.exe`。
3. `C:\Program Files (x86)\FFmpeg\ffmpeg-7.1.1-essentials_build\bin\ffmpeg.exe`。

## 整理歌单

在项目根目录运行：

```powershell
python `
  .\tools\prepare_music.py `
  --source 'D:\你的原始歌单' `
  --output '.\music'
```

需要重新生成已有输出时加入：

```powershell
--overwrite
```

需要显式指定 FFmpeg 时加入：

```powershell
--ffmpeg 'C:\路径\ffmpeg.exe'
```

## 输入与输出

工具会递归扫描 MP3、WAV、FLAC、M4A、AAC、OGG、OPUS、WMA，以及包含音轨的
MP4、FLV、MKV、MOV 和 WEBM，并将结果平铺到输出目录：

```text
music/
├── 歌曲A.mp3
├── 歌曲A.lrc
└── 歌曲B.mp3
```

- 音频统一为 44.1 kHz、双声道、320 kbps MP3。
- 视频文件固定提取第一条音轨，忽略视频、字幕和数据流；没有音轨时将该文件报告为失败。
- 使用两遍 FFmpeg `loudnorm`，目标约为 `-16 LUFS`、`-1.5 dBTP`。
- 同名 LRC 会统一转为 UTF-8；没有 LRC 时仍然输出歌曲。
- 输出文件名保留原名主体，并清理 Windows 非法字符；重名时追加 ` (2)`、` (3)`。
- 输出目录是扁平结构，不保留源目录层级。
- 原始文件永远不会被修改、移动或删除。
- 默认跳过已有输出；`--overwrite` 只覆盖输出目录中的派生文件。
- 源目录和输出目录不能相同，也不能互相包含。

处理完成后会在输出目录生成 `prepare_music_report.txt`。单首歌曲失败不会阻止其他歌曲继续处理。

## 转换 PotPlayer DPL 歌单

`tools/convert_dpl_playlist.py` 读取 PotPlayer 的文本 DPL，只提取
`序号*file*完整路径` 记录中的文件名，并生成播放器可读取的 UTF-8 歌单。它不会检查
音乐或歌词文件是否存在。

例如，将 DPL 转到 Release 目录的多歌单文件夹：

```powershell
python `
  .\tools\convert_dpl_playlist.py `
  --source 'D:\歌单\260427_likes.dpl' `
  --output '.\build-release\playlists\260427_likes.txt'
```

输出内容固定按同名歌词生成：

```text
中文歌曲.mp3|中文歌曲.lrc
English Song.mp3|English Song.lrc
```

- 不传 `--output` 时，在 DPL 旁生成同名 `.txt`。
- 输出文件已存在时默认拒绝覆盖；确认覆盖时加入 `--overwrite`。
- 只转换 MP3 记录；同名歌曲只保留第一次出现的记录。
- 支持 UTF-8、UTF-8 BOM、UTF-16 和 GB18030 DPL。
- 纯音乐可在转换后手动把歌词文件名改成 `-`。
- 转换成功退出码为 `0`，输入、格式或输出错误为 `2`。

## 歌单预处理工具退出码

- `0`：没有歌曲转换失败，允许存在缺少歌词等警告。
- `1`：至少一首歌曲失败，或报告无法写入。
- `2`：参数、目录或 FFmpeg 等启动条件错误。
- `130`：用户按 Ctrl+C 中断。

## 批量生成歌词草稿

`tools/generate_lrc.py` 可以识别单个音频文件，也可以递归扫描输入目录，用本地
whisper.cpp 识别歌曲，并在输出目录生成同名 UTF-8 LRC 草稿。输入歌曲不会被修改。

例如：

```text
D:\待识别歌曲\歌手A\歌曲.mp3
        ↓
D:\生成歌词\歌手A\歌曲.lrc
```

工具保留相对子目录，只把音频扩展名改为 `.lrc`。这样不同子目录中的同名歌曲
不会互相覆盖。如果同一目录中存在 `歌曲.mp3` 和 `歌曲.flac`，二者会映射到同一个
LRC，工具会将这两首都报告为失败，不擅自改名。源目录和输出目录不能相同，也不能
互相包含。

### 下载 whisper.cpp 和模型

本机 RTX 4060 可以使用 whisper.cpp v1.9.1 的 CUDA 12.4 版。下面的命令会显示
实时下载进度。工具优先使用完整 `large-v3` 模型；未安装时才回退到现有的
`large-v3-turbo-q5_0` 量化模型。

先下载并解压 whisper.cpp：

```powershell
$whisperRoot = Join-Path $PWD 'tools\whisper'
New-Item -ItemType Directory -Path $whisperRoot -Force | Out-Null
curl.exe --fail --location --progress-bar `
  'https://github.com/ggml-org/whisper.cpp/releases/download/v1.9.1/whisper-cublas-12.4.0-bin-x64.zip' `
  --output (Join-Path $whisperRoot 'whisper-cuda.zip')
Expand-Archive -LiteralPath (Join-Path $whisperRoot 'whisper-cuda.zip') `
  -DestinationPath $whisperRoot -Force
```

下载识别质量优先的完整 `large-v3` 模型，约 3.1 GB；命令支持中断后继续下载：

```powershell
$modelRoot = Join-Path $PWD 'tools\whisper\models'
New-Item -ItemType Directory -Path $modelRoot -Force | Out-Null
curl.exe --fail --location --progress-bar --continue-at - `
  'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3.bin?download=true' `
  --output (Join-Path $modelRoot 'ggml-large-v3.bin')
Get-FileHash -Algorithm SHA256 `
  (Join-Path $modelRoot 'ggml-large-v3.bin')
```

完整模型的 SHA-256 应为：

```text
64d182b440b98d5203c4f9bd541544d84c605196c4f7b845dfa11fb23594d1e2
```

如果暂时只使用速度更快、约 574 MB 的量化模型：

```powershell
$modelRoot = Join-Path $PWD 'tools\whisper\models'
New-Item -ItemType Directory -Path $modelRoot -Force | Out-Null
curl.exe --fail --location --progress-bar `
  'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo-q5_0.bin?download=true' `
  --output (Join-Path $modelRoot 'ggml-large-v3-turbo-q5_0.bin')
Get-FileHash -Algorithm SHA256 `
  (Join-Path $modelRoot 'ggml-large-v3-turbo-q5_0.bin')
```

量化模型的 SHA-256 应为：

```text
394221709cd5ad1f40c46e6031ca61bce88931e6e088c188294c6d5a55ffa7e2
```

这些文件只供本机使用，不应提交到版本库。

### 运行识别

在项目根目录运行：

```powershell
python `
  .\tools\generate_lrc.py `
  --source 'D:\待识别歌曲' `
  --output 'D:\生成歌词'
```

只识别或更新一首歌时，直接把 `--source` 指向音频文件：

```powershell
python `
  .\tools\generate_lrc.py `
  --source 'D:\待识别歌曲\歌曲.mp3' `
  --output 'D:\生成歌词' `
  --overwrite
```

这会生成 `D:\生成歌词\歌曲.lrc`。首次增加歌词且目标不存在时可以省略
`--overwrite`；更新已有歌词时必须加入它。单文件模式允许输出目录就是歌曲所在目录，
因此也可以直接在原歌曲旁边生成同名 LRC，音频本身不会被修改。

也可以双击 `tools\update_one_song_gui.pyw` 打开单曲更新小窗口。首次使用前，先复制
本机配置模板：

```powershell
Copy-Item `
  .\tools\update_one_song.local.example.ini `
  .\tools\update_one_song.local.ini
```

在 `update_one_song.local.ini` 的 `[Paths]` 中填写实际音乐和歌词目录；需要使用
DeepSeek AI 辅助修复时，再在 `[DeepSeek]` 中填写新申请的 `ApiKey`。不使用 AI 时
可以保持 `ApiKey` 为空。本机 INI 已被 Git 忽略，不得把真实 API Key 写回源码、示例
配置或提交记录；Key 一旦泄露，应立即在服务商控制台撤销并换新。

输入歌曲名、选择本首歌的初次识别语言后点击“开始”，程序会从本机 INI 指定的音乐
目录查找歌曲，并将结果覆盖更新到指定歌词目录。歌曲名可以输入
`忘川彼岸DJ`，也可以输入 `忘川彼岸DJ.mp3`；遇到同名但扩展名不同的文件时，必须
输入带扩展名的完整名称。识别期间按钮会显示进度，完成或失败后会弹窗提示。这个
窗口及其调用的歌词脚本兼容本机默认的 Python 3.8，也可以继续使用 Python 3.12。

“初次识别语言”默认选择中文，也可以选择自动检测、英语、日语、韩语、粤语、法语、
德语、西班牙语、俄语、意大利语或葡萄牙语。这个选择只控制 Whisper 的初次识别；
勾选 AI 辅助修复时，DeepSeek 仍会根据识别草稿和粘贴的参考歌词完成校对。

歌曲本身确实包含大量相同歌词时，可以勾选“允许大量重复歌词（确认属于歌曲原词）”。
默认不勾选时，工具仍会拒绝疑似模型循环幻觉；勾选后只跳过通用重复次数判定，仍然
过滤字幕水印、制作信息和纯音乐占位，并在报告中记录警告。该选项允许正常生成 LRC，
也允许继续执行后续的 DeepSeek AI 辅助修复。

勾选“AI 辅助修复”后，在下方输入框粘贴完整的无时间戳参考歌词。工具先生成带时间
戳的 Whisper LRC，再通过 DeepSeek 在线接口结合两份内容修正错别字、分行和遗漏，
最后校验并覆盖刚生成的 LRC。接口或返回内容异常时不会覆盖文件，而是保留 Whisper
版本并弹窗说明。DeepSeek 使用 `deepseek-v4-pro` 在线模型，并通过
`NO_PROXY=api.deepseek.com` 绕过代理直连；模型不需要下载，API Key 只从被 Git
忽略的 `tools/update_one_song.local.ini` 读取。

默认自动判断语言。歌曲语言统一时可以明确指定，例如中文：

```powershell
--language zh
```

已有同名 LRC 默认跳过；需要重新识别时加入：

```powershell
--overwrite
```

如果没有使用上述默认目录，也可以显式指定：

```powershell
--whisper 'D:\工具\whisper-cli.exe' `
--model 'D:\模型\ggml-large-v3-turbo-q5_0.bin'
```

工具支持 MP3、WAV、FLAC、M4A、AAC、OGG、OPUS 和 WMA。识别前会通过
FFmpeg 转成临时的 16 kHz 单声道 WAV，处理完成后自动删除临时文件。单首失败
不会中止其余歌曲；终端会显示当前歌曲、识别百分比和成功/跳过/失败汇总，输出目录
会生成 `generate_lrc_report.txt`。

所有歌曲默认直接使用完整抗幻觉参数：关闭温度回退、抑制非语音 token、禁用前文
累积上下文，并根据文件名提供歌词提示。输出后还会过滤常见字幕水印以及以“作词、
作曲、编曲、演唱、歌手、制作人”开头的制作信息。若同一句内容高频或连续重复，工具
会将该歌曲判定为识别失败并拒绝输出，避免把循环幻觉当成成功歌词。
`Music`、`Instrumental`、`Zither Harp`、`纯音乐`、`间奏` 等纯音乐标签也会被过滤。

生成结果是自动识别草稿，不等同于官方歌词。重伴奏、合唱、Rap、拖长音、方言和
混响都可能造成错字、漏词或时间偏差，建议使用前人工快速校对。少数中文 token
可能被 whisper.cpp 输出为不完整的 UTF-8 字符；工具会将该处写成 `�`、报告警告并
继续生成 LRC，不会再让整首歌失败。`�` 所在位置需要人工补回正确歌词。

## 标记异常纯音乐歌词

`tools/mark_instrumental_lrc.py` 用于扫描一个歌词目录，把明显由模型幻觉产生的纯音乐
LRC 标记成播放器支持的 `#INSTRUMENTAL`。它会保守识别重复字幕水印、重复制作信息、
纯音乐占位词和极端单句循环。按当前曲库规则，只要文件有时间戳歌词但总数不足 10 行，
就直接列为候选；达到 10 行后，如果全文不超过 3 种内容，并且同一句至少出现 6 次且
占比达到 70%，也会列为候选。正常副歌重复不会仅因出现几次就被修改。

先只预览候选，不修改任何 LRC：

```powershell
python `
  .\tools\mark_instrumental_lrc.py `
  --source 'D:\歌词目录'
```

检查终端候选和目录中的 `mark_instrumental_report.txt` 后，再执行替换：

```powershell
python `
  .\tools\mark_instrumental_lrc.py `
  --source 'D:\歌词目录' `
  --apply
```

默认只扫描目录第一层；需要处理子目录时加入 `--recursive`。`--apply` 只原子替换被
判定为异常的 LRC，内容固定为一行 `#INSTRUMENTAL`；其他 LRC 不会改动。自动判断不
可能百分之百准确，因此必须先运行预览并人工确认候选，再执行替换。

歌词工具退出码：

- `0`：全部成功或按规则跳过。
- `1`：至少一首失败，或报告写入失败。
- `2`：参数、目录、FFmpeg、whisper.cpp 或模型等启动条件错误。
- `130`：用户按 Ctrl+C 中断。

## 当前边界

- 不整理 ID3 标题、歌手、封面等元数据。
- 歌单预处理工具不下载、识别或编辑歌词；歌词识别由独立工具完成。
- 不在播放器中执行转码或响度归一化。
- 不提交原始歌曲、转换结果、FFmpeg、whisper.cpp 或模型文件。

## 构建基础播放器

使用 Qt Creator 打开项目根目录的 `on_screen_music.pro`，选择 Qt 5.14 MinGW 7.3 64 位 Kit，以 Release 配置构建并运行。

也可以在已经配置 Qt 工具路径的 PowerShell 7 中执行影子构建：

```powershell
New-Item -ItemType Directory -Path '.\build-release' -Force | Out-Null
Push-Location '.\build-release'
$env:Path = 'D:\Qt\Qt5.14.0\Tools\mingw730_64\bin;D:\Qt\Qt5.14.0\5.14.0\mingw73_64\bin;' + $env:Path
& 'D:\Qt\Qt5.14.0\5.14.0\mingw73_64\bin\qmake.exe' '..\on_screen_music.pro' 'CONFIG+=release'
& 'D:\Qt\Qt5.14.0\Tools\mingw730_64\bin\mingw32-make.exe' -j8
Pop-Location
```

## v1.0 稳定目录

项目根目录的 `release-v1.0` 是播放器的稳定运行目录。里面已经放入 Release EXE、Qt 5.14 动态库、MinGW 运行库以及 Windows 平台和音频插件，不包含编译中间文件，也不包含 FFmpeg。

默认将自己的内容分别放入：

```text
release-v1.0/
├── OnScreenMusic.exe
├── playlists/
├── music/
└── lyrics/
```

当前只整理程序运行环境，不复制个人歌曲、歌词或歌单数据。播放器源码仍在项目根目录和 `src`，不要在 `release-v1.0` 中进行开发。

播放器默认读取 `OnScreenMusic.exe` 旁边 `playlists` 目录中的 UTF-8 `.txt` 歌单，音乐和歌词分别放在 `music`、`lyrics`。也可以从托盘“资料目录”选择另一个根目录；所选目录必须已经包含这三个可读取的子目录，程序不会创建、移动或复制其中的文件。开发构建后，目录类似：

```text
build-release/
├── OnScreenMusic.exe
├── playlists/
│   ├── 日常.txt
│   └── 纯音乐.txt
├── music/
    ├── 歌曲A.mp3
    └── 歌曲B.mp3
└── lyrics/
    └── 自定义歌词名.lrc
```

每个歌单文件每行写一首歌，使用 `|` 分隔音乐文件名和歌词文件名；无歌词写 `-`：

```text
# 空行和以 # 开头的行会忽略
歌曲A.mp3|自定义歌词名.lrc
歌曲B.mp3|-
```

- 文件使用 UTF-8，可带 BOM。
- 只加载列表中明确写出的 `.mp3`；文件名不能包含目录路径。
- 音乐缺失或行格式错误时跳过该行；指定歌词缺失时仍播放音乐，主歌词区域显示 `_`。
- 同一音乐可重复写多行来增加随机权重：写两行相当于普通歌曲的两倍抽中概率。重复行必须使用相同的歌词配置；配置不一致时不增加权重，并在“歌单检查”窗口中报告。选歌列表仍只显示一首。
- `playlists` 只扫描第一层，歌单按文件名排序。
- `playlists` 没有 `.txt` 时，根目录旧版 `playlist.txt` 会作为兼容回退。
- 预处理工具保持原有行为，不自动创建目录结构或歌单文件，整理结果由用户手动放置。
- 加载或切换歌单时，如果发现音乐/歌词缺失、行格式错误、文件名无效或重复歌曲的歌词配置不一致，程序会把全部问题汇总到一个“歌单检查”窗口；内容可以选中复制，正常的同配置重复权重行不会弹窗。

首次启动会从歌单中完全独立随机载入一首并保持暂停；以后启动恢复上次歌单、歌曲和播放点，但仍保持暂停。点击歌词层的 `▶` 或按 `左Ctrl+Num5` 后才开始播放。随机允许连续抽到同一首。LRC 支持 `[mm:ss]`、`[mm:ss.xx]`、`[mm:ss.xxx]` 和一行多个时间标签。歌曲文件名主体固定显示在进度条同一行的最左侧，名称过长时以省略号截断，悬停可查看完整名称。

播放器只允许一个实例运行；重复启动时会提示“On Screen Music 已经在运行”，不会出现两个播放器同时播放或争用快捷键。

## 状态保存位置

播放器的全部持久状态都保存在 `OnScreenMusic.exe` 旁边可见的 UTF-8 `OnScreenMusic.ini`，不再使用 Windows 注册表：

```ini
[Library]
Root=D:/OnScreenMusicData
PlaylistFile=日常.txt

[Playback]
AudioFile=歌曲A.mp3
PositionMs=123456

[Audio]
Volume=14

[Window]
Position=@Point(100 200)
```

保存内容如下：

| 设置项 | 内容 |
| --- | --- |
| `Library/Root` | 可选资料根目录；缺省时使用 EXE 所在目录 |
| `Library/PlaylistFile` | 当前歌单文件名 |
| `Playback/AudioFile` | 当前音乐文件名 |
| `Playback/PositionMs` | 当前播放位置，单位为毫秒 |
| `Audio/Volume` | 主音量 |
| `Window/Position` | 歌词窗口屏幕坐标 |

托盘“资料目录”可以选择新目录或恢复程序所在目录。未配置或恢复默认时，程序继续读取 EXE 旁的 `playlists`、`music`、`lyrics`；配置的目录不可用时会明确提示，并在本次运行中临时回退到程序所在目录。切换资料目录后重新读取歌单并保持暂停。

播放期间约每两秒保存一次，并在暂停、跳转播放点、切歌、切换歌单、调节音量、移动窗口和正常退出时保存。程序启动后恢复这些值，但仍保持暂停和未隐藏。移动程序时应让 INI 与 EXE 一起移动；资料根目录使用绝对路径时，移动 EXE 不会改变资料位置。

如果要完全重置播放器，应先退出程序，再删除 `OnScreenMusic.ini`。不要在程序运行时手工修改 INI，因为退出保存可能覆盖修改。

纯音乐即使在歌单中配置了 LRC，也可以在该 LRC 第一行写入：

```text
#INSTRUMENTAL
```

程序会忽略标记的大小写、UTF-8 BOM 和首尾空格。检测到标记后不再解析后续歌词，整首只在歌词区域居中显示 `_`；标记必须位于文件第一行。没有配对歌词、歌词文件缺失或没有有效歌词的歌曲，以及有效歌词开始前，也统一显示 `_`，不再把歌曲名放在主歌词区域。每句歌词最多显示 5 秒；距离该句时间戳达到 5 秒且尚未进入下一句时显示 `_`，最后一句也会在 5 秒后变为 `_`。

歌词层每次启动都默认解锁，可以直接点击按钮、拖动进度和拖动窗口。未隐藏时，在歌词层任意位置（包括按钮、进度条和文字）按住鼠标中键都能移动整个窗口，松开后保存位置；隐藏穿透时需先通过快捷键或托盘恢复。歌词始终保持单行，不会自动换行或撑高悬浮层；短歌词使用最大 60 px 字号，较长歌词会自动选择能够完整放入当前宽度的最大字号。点击“隐藏”后会透明化控件并让整个歌词层鼠标穿透，同时保留控制条的布局空间，因此歌词位置不会变化；隐藏状态不会跨启动保存。所有控制按钮尺寸相同，歌词靠近下方进度条显示，最右侧“关闭”按钮会直接退出程序。程序会保存歌单、歌曲、播放点、窗口位置和音量。选歌按钮会打开带搜索框的歌曲列表，选歌单按钮会打开临时歌单列表，`🔊` 会打开小型音量滑块，音量范围限制为 Qt 原始音量的 0–20%。

进度条支持点击任意位置直接跳转，也可以按住滑块拖动。“刷新”按钮会重新扫描 `playlists` 并重读当前歌单和当前歌曲的 LRC：当前歌曲仍有效时保持播放/暂停状态和播放点；歌曲已被移除或变成无效配置时，从刷新后的歌单随机载入一首并保持暂停。刷新只在点击按钮时执行，不进行后台文件轮询。

固定全局快捷键：

- `左Ctrl+Num5`：播放/暂停。
- `左Ctrl+Num4`：下一首。
- `左Ctrl+Num6`：隐藏或恢复歌词层控件。
- `左Ctrl+Num1`：回退 5 秒。
- `左Ctrl+Num3`：快进 5 秒。

快捷键通过 Windows Raw Input 在后台接收左 Ctrl 和数字小键盘 1/3/4/5/6 的物理扫描码，NumLock 开启或关闭都可使用，同时不会占用主键盘的方向键；右 Ctrl 不参与播放器快捷键，也不提供音量和选歌全局快捷键。按键处理完全由事件驱动，不进行持续轮询，也不会吞掉按键，因此播放器和当前游戏可能同时响应同一组合键。Num1、Num3、Num4 按下时立即执行一次，持续按住 500 ms 后开始重复；Num1/Num3 每 200 ms 重复，Num4 每 700 ms 重复。Num5 和 Num6 长按不重复。释放数字键或左 Ctrl 后，当前重复立即停止。快进和回退会限制在 `00:00` 与歌曲总时长之间，暂停时跳转后仍然保持暂停。

系统托盘最上方显示当前快捷键模式：默认的“全部快捷”表示五组快捷键均启用；点击后变为“播放专用”，此时播放器仅响应 `左Ctrl+Num5`，忽略其余四组。再次点击恢复全部快捷键。该模式每次启动默认关闭且不保存，也不显示勾选标记。切换模式会停止正在进行的长按操作。托盘“资料目录”用于选择或恢复资料根目录，其余项目为“锁定窗口/解锁窗口”、“隐藏窗口/显示窗口”、“软件说明”和“退出软件”。“软件说明”显示 On Screen Music v1.0、制作时间、制作者及上述基本用法，不联网，也不检查更新。

若物理小键盘快捷键初始化失败，系统托盘会提示，其他功能不受影响。
