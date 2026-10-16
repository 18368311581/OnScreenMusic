# 历史命令与开发参考

本文件保留此前完整说明，包含本机路径和历史版本背景；当前用户操作以根目录 README 和 USER_GUIDE 为准。

# On Screen Music

这是一个 Windows 本地桌面歌词播放器项目。桌面播放器核心功能已完成并定为 v1.0，后续以修复真实问题为主；歌词生成、歌词优化、歌单整理和音频预处理等附属工具仍可继续开发。

`README.md` 面向实际使用和构建，记录命令、目录和操作方法；`AGENTS.md` 面向后续开发协作，记录技术约束、职责边界和验证要求，两者用途不同。

应用图标源文件位于 `assets/app_icon.png`，Windows 多尺寸图标位于 `assets/app_icon.ico`；构建时会嵌入 EXE，并用于应用窗口和系统托盘。

## 环境

- Windows 11。
- Python 3.12；音乐管理界面需要 PySide6（本机已有 6.11.2 / Qt 6.11.2），其他命令行工具使用标准库。
- 本机 FFmpeg 7.1.1，并包含 `loudnorm` 和 `libmp3lame`。
- Qt 5.14、Qt Creator、MinGW 7.3 64 位 Kit。

项目不会打包 FFmpeg。工具会依次查找：

1. `--ffmpeg` 指定的文件。
2. PATH 中的 `ffmpeg.exe`。
3. `C:\Program Files (x86)\FFmpeg\ffmpeg-7.1.1-essentials_build\bin\ffmpeg.exe`。

## Music Workshop 音乐管理 v0.7.1

音乐管理是独立的 Python 3.12 + PySide6（Qt 6 Widgets）桌面软件，统一操作音频预处理、
本地歌词识别、参考歌词 AI 校对、歌词编辑和歌单管理。播放器托盘“音乐管理”只打开
同目录启动文件，不传递播放状态或控制消息。资料写入后，播放器点击“刷新”即可重读。
侧栏五个页面使用对应功能的小图标，不再显示“资料与工具”小标题；窗口标题栏与界面顶部共用蓝色 M 图标，图标支持深浅色与高分屏显示。

### 启动与目录

便携目录包双击 `MusicWorkshop.exe`，无需另装 Python。`MusicWorkshopTool.exe` 用于后台处理和可见的下载命令行，两者与 `MusicWorkshopRuntime` 目录保持完整；运行时资料仍在 EXE 同目录。
两个 EXE 共用运行库，大小相近是因为包含相同的程序模块，区别在于主程序打开图形界面，Tool 入口支持后台命令及控制台输出。日常只打开主程序，不要删除 Tool 文件。

源码版双击播放器旁的 `MusicWorkshop.vbs`。启动文件使用本机当前用户目录中的 Python 3.12，
不会打开控制台。该环境须包含 PySide6；本机已有 6.11.2 / Qt 6.11.2。
缺少界面依赖时，在对应 Python 3.12 环境运行 `python -m pip install -r requirements-workshop.txt`。

开发入口也读取现有 `release-v1.0` 部署目录的统一配置与资料。代码部署命令：

```powershell
pwsh -File .\tools\deploy_workshop.ps1 -Destination .\release-v1.0
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" .\MusicWorkshop.pyw
```

部署脚本只复制明确列出的程序源码与界面图标，不复制媒体、Whisper、模型、FFmpeg 或凭据。
本机现有 Whisper 文件夹已经直接移动到下列位置，没有另外保留重复副本。

```text
release-v1.0/
├── OnScreenMusic.exe
├── MusicWorkshop.vbs
├── MusicWorkshop.pyw
├── requirements-workshop.txt
├── workshop/                         # 独立工作台模块和界面图标
├── tools/
│   ├── *.py                          # 处理脚本
│   ├── ffmpeg/bin/ffmpeg.exe          # 可选：在参数设置中下载
│   └── whisper/
│       ├── Release/whisper-cli.exe    # 连同同目录所需 DLL
│       └── models/ggml-large-v3.bin
├── OnScreenMusic.ini                 # 唯一配置，含本机凭据，禁止提交
├── MusicWorkshopWork/                # 固定工作目录，禁止提交
├── music/*.mp3
├── lyrics/*.lrc
└── playlists/*.txt
```

资料根目录固定为软件所在目录，工作目录固定为其中的 `MusicWorkshopWork`。
Whisper 和模型默认按上述相对位置查找；保存在软件目录内的工具路径使用相对位置，整体移动文件夹后仍可读取。
三个资料子目录须已经存在，程序不会自动移动或复制音乐资料。
FFmpeg、本地识别程序和本地识别模型各自提供文件选择、独立保存、自动查找和下载。
“自动查找”优先复用已配置或软件目录中的文件，也会查找系统已有程序；找到后只保存该项。
“下载”打开独立命令行窗口，下载、校验并安装到上述默认位置，成功后自动保存该项配置；界面不显示下载进度条。
窗口显示下载信息，按 Ctrl+C 可中止；完成或失败后按回车关闭。支持服务器允许的断点续传，已有工具或模型直接复用。
large-v3 模型约 3.1 GB，点击其下载按钮才会下载。下载功能不修改系统 PATH，也不安装 Python 包。
FFmpeg 使用[官网推荐的 Windows 构建来源 Gyan](https://www.ffmpeg.org/download.html)，识别程序使用
[whisper.cpp 发布包](https://github.com/ggml-org/whisper.cpp/releases)，模型使用
[官方模型仓库](https://huggingface.co/ggerganov/whisper.cpp/blob/main/ggml-large-v3.bin)。部署源码时仍不打包这些文件。
DeepSeek Key 单独保存，无改动时对应保存按钮置灰；工具下载完成后的配置刷新会保留其他尚未保存的输入。
“清理临时文件”会先在后台统计占用，再由用户选择并确认清理。默认只清理无用写入副本和中断任务的临时目录；下载缓存、历史备份分别勾选。任务的已保存音频、歌词结果、参考歌词、任务记录、已安装工具及模型保留。处理或下载期间禁止清理，统计后发生变化或被占用的文件跳过；不跟随目录链接。之后的正常歌词/歌单保存会自动移除本次写入副本，减少积累。
目录设置不再使用 `Library/Root` 和 `Workshop/Work`，也不读取旧 `MusicWorkshop.local.ini`。

两部分共用 `OnScreenMusic.ini`，写入时协调并发保存并保留播放器及未知字段。
“参数设置”页面底部同一行提供等宽的“使用说明”和“关于”按钮；使用说明为本地 HTML 页面，关于窗口显示版本、制作者与软件介绍。
“关于”后面的“切换深色 / 切换浅色”按钮立即切换整个工作台及其弹窗的样式，保留未保存编辑。
选择自动保存到共享配置的 `Workshop/Theme`，下次启动恢复；不改变桌面播放器的外观。
Qt 5.14 播放器与 Qt 6 工作台分别在独立进程运行。密钥只保存在 `Workshop/ApiKey`，不进入报告。
本地识别不上传音频；在线 AI 校对仅发送歌曲名、歌词草稿和参考歌词，产生正常接口用量。

### 处理歌曲

1. 三个入口：“添加文件”“添加文件夹”“选择现有歌曲”；现有歌曲可搜索并多选。
2. 每一行独立设置“统一格式与响度”“本地识别歌词”“AI 校对”“允许大量重复歌词”，设置按歌曲保存。同一批歌曲可以使用不同的处理步骤；顶部识别语言用于本次所选任务。
3. 现有歌曲行的音频转换固定置灰且取消勾选，保留原 MP3；新文件默认勾选转换，其他选项默认关闭。进行中的歌曲不能修改选项。
4. 每行“参考歌词”列通过“填写 / 已填写”按钮打开独立编辑窗口，保存后仅更新这首歌的参考歌词，取消保留原内容；底部不再常驻参考歌词区。
5. 只做 AI 校对时使用已有的同名歌词；没有歌词时同时勾选本地识别。
6. 同时勾选识别与 AI 时，按识别 → AI 顺序执行，AI 使用本次识别的新草稿。新文件勾选转换时先转码。
7. 选择歌曲并满足处理条件后，“开始所选处理”才启用；未选歌、未选择有效步骤、缺少 AI 密钥或参考歌词、没有可校对的歌词、包含正在处理的任务等情况下置灰，悬停查看原因。
8. 整项处理成功后，识别或 AI 校对的最终歌词自动写入 `lyrics` 中对应的 LRC，无需审阅或采用。AI 与识别同时启用时只写入最后的 AI 结果；失败或终止不替换原歌词。已有 LRC 覆盖前自动保存旧版备份；转换产生的 MP3 仍保存在工作目录，原始音频不改动。本页不提供“加入歌单”和“导出所选结果”。
9. 每行右侧 `×` 可从处理列表移除该歌曲，只更新对应行并保留滚动位置，保留原文件、已保存结果和任务记录。顶部“移除全部”一次移除所有未在处理的条目；排队、处理或终止中的条目会保留，需先在任务记录中终止。
10. “允许重复”仅在该行勾选本地识别后可用；确认大量重复确属原歌词时勾选，可放行重复检查，其他歌曲仍按各自设置处理。该开关不构成独立处理步骤，也不会关闭无有效歌词等检查。

本页不提供“审阅当前结果”按钮，工作目录保留处理结果，最终歌词成功后自动生效；桌面播放器点击刷新重读。

音频沿用两遍 loudnorm、44.1 kHz、双声道、320 kbps MP3；视频固定提取第一条音轨。
无法解码的素材保留错误原因，不把改扩展名当作修复。
默认 AI 校对严格保留时间标签，歌词时间的手动修改仍须试听确认。
重新识别或校对成功时保留先前候选的归档；失败和终止不提交未完成的派生结果。
真实歌曲识别、版本匹配和歌词时间仍须人工确认；当前没有波形或逐句试听。

### 歌曲资料与歌词编辑

“歌曲资料”主页只显示可搜索的歌曲列表和逐行“编辑歌词”按钮，不显示歌词状态、歌单筛选或跨页跳转按钮。
资料库独立扫描 `music` 第一层的 MP3，不读取歌单；选中、搜索和打开歌词均不会创建处理任务。
每行“编辑歌词”打开一个编辑框，直接读取 `lyrics` 下与音乐同名的 LRC，不读取歌单中的自定义映射、工作候选或草稿。无歌词文件时可从空白开始编辑。
无改动时“保存”置灰；修改、撤销、还原内容时按实际差异更新按钮，保存后重新置灰。“保存”直接写入对应 LRC，自动备份原文件，并在原文件被外部修改、删除或新建时拒绝覆盖。
原始歌词、修改对比、保存到工作目录、采用和另存等多层操作已移除。仍可手动调整时间偏移、标为纯音乐；文本按编辑内容写入 UTF-8，保留空行与空格。
关闭窗口或按 Esc 时，可保存、放弃或取消关闭；保存手动编辑不会覆盖处理任务的 AI 参考歌词。识别和 AI 校对统一在“处理歌曲”进行。
试听直接在编辑窗口内播放，提供播放/暂停、可点击或拖动的进度条、当前位置/总时长和音量。点击轨道即可跳到对应位置，也可按住继续拖动；操作时预览目标时间，松开后仅跳转一次，并保持原先的播放或暂停状态。打开窗口不自动播放，关闭窗口即停止并释放音频文件。
试听使用 Windows 自带音频能力，不启动外部播放器、不新增第三方依赖；试听音量默认 20%，与桌面播放器独立。播放出错时在窗口内提示，仍可继续编辑和保存歌词。

### 歌单列表

“歌单管理”可选择 TXT 歌单自动载入，也可新建或导入 PotPlayer DPL；取消未保存编辑的切换时保留原歌单。
顶部“保存歌单”在没有改动时置灰，修改后启用；保存或还原改动后重新置灰。输入已有歌单名后按 Enter 也可载入。
旁边“删除歌单”仅对已载入的 TXT 可用，确认后先备份再删除该歌单文件，同时放弃当前未保存编辑；歌曲和歌词保留。
备份位于 `MusicWorkshopWork/backups/<编号>/`，包含原 TXT 与记录原位置的 `restore.json`。
每首歌曲使用紧凑无外框的一行，行内直接调整 1–10000 的正整数权重，选择是否加载歌词，或点 `×` 移除引用。
删除只更新对应行，保留当前滚动位置。列表最后一行的大 `＋` 打开添加窗口，不常驻底部表单。
下拉列表统一为最多显示 12 行的平整列表，行距加宽；添加歌曲时可直接选择，也可输入歌名开头筛选。例如输入 `F` 只显示 `F` 开头的歌曲；
输入不存在或不完整的名称不能确定，同一首歌不能重复添加。选定完整歌名后点“添加”，取消不会更改歌单。
歌曲按中文名称与数字自然排序，例如 `F2` 排在 `F10` 前面。

保存仍使用播放器既有 `音乐文件名|歌词文件名` 格式：权重编码为重复行，取消歌词使用 `-`。
已有注释和自定义歌词映射保留；移除引用不删除歌曲或歌词。
打开歌单时会自动检查，结果显示在歌单管理顶部；歌曲资料页不再提供“歌单检查”按钮。
存在格式错误、音乐或歌词文件缺失、同一歌曲歌词配置冲突时，显示“自动修复”按钮。
自动修复仅从当前编辑中删除错误行，保留有效歌曲的重复权重行、注释及歌词开关；点击“保存歌单”后才写入文件，并保留原歌单备份。
未修复错误时保存按钮置灰；切换歌单、关闭软件时沿用未保存编辑提示。歌曲和歌词文件不会删除。
界面不再提供原始文本编辑、跨页面选歌、添加/设置所选歌曲、移除所选引用和手动检查引用按钮。

### 任务列表

任务页显示任务总数和进行中的数量，每个处理任务占一行。
多步骤任务的进度条按已完成步骤前进，并显示当前步骤；单步骤运行时显示动态进度条，
不把无法测量的识别进度显示成估计百分比。

- 进行中点 `×`，确认后只终止这一项；其他任务继续。排队中的任务可立即终止。
- 转换、识别和 AI 输出先写临时区，整项成功才提交到工作结果；终止时丢弃未完成输出。
- 成功、失败及终止记录持续保留。失败行显示简短原因，不提供重试按钮。
- 歌词处理成功显示“完成 · 歌词已更新”；只转换音频时提示结果已保存到工作目录，不再提示待审阅。
- 结束后按钮变成 `⌫`，删除该任务记录；已保存的工作结果、歌曲和歌词保留。
- 退出软件时可以停止所有任务；异常中断记录在下次启动标为已终止。

原始音频素材保持不变。用户发起的识别和 AI 校对会在整项成功后自动更新资料库歌词，手动歌词/歌单保存按对应操作生效；替换前在工作目录 `backups/<编号>/`
保留旧文件和 `restore.json` 原位置记录。清理对话框默认不勾选历史备份，选中并删除后将无法恢复旧版本。
资料库中的任务路径按软件根目录相对保存；从外部导入的原始素材仍指向其实际位置。

### 验证

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -X utf8 -m unittest discover -s tests
```

测试使用临时目录，覆盖真实 FFmpeg 转换、原素材保护、单任务终止、整项结果提交、队列继续、
路径随目录移动、Qt 行内歌单编辑、前缀补全、重复拒绝、共享配置和退出保存。
AI 请求使用模拟响应；自动测试不替代真实歌曲、托盘点击与实际试听验收。

### 目录式打包与启动测量

构建环境使用 Python 3.12、项目界面依赖和 PyInstaller 6；仅构建时需要 PyInstaller，用户运行无需安装。
本机的独立构建环境为 `.packaging-venv`，不修改系统 Python 或 PATH。

```powershell
pwsh -File .\tools\package_workshop.ps1
python .\tools\benchmark_workshop_startup.py --root .\release-v1.0 --runs 5
python .\tools\benchmark_workshop_startup.py --root .\release-v1.0 --executable .\dist-workshop\MusicWorkshop\MusicWorkshop.exe --runs 5
```

打包使用明确的播放器文件清单和独立的管理程序运行目录；不会带入个人 INI、歌曲、歌词、模型、任务记录、旧程序备份和日志。
`packages` 下生成首次使用说明和空资料目录，作为便携测试包。启动测量记录从进程创建到首次 Qt 窗口绘制，不包含冷开机、桌面合成显示或用户双击到进程创建的时间；500 毫秒是优化目标，不是兼容性保证。

## 整理歌单

在项目根目录运行：

```powershell
python `
  .\tools\prepare_music.py `
  --source 'D:\你的原始歌单' `
  --output '.\music'
```

只处理一个音频或视频文件时，直接把 `--source` 指向该文件：

```powershell
python `
  .\tools\prepare_music.py `
  --source 'D:\待处理\单曲.flac' `
  --output '.\music'
```

单文件模式会输出 `单曲.mp3`，同目录存在 `单曲.lrc` 时也会转换并复制为 UTF-8。
如果输入本身是 MP3，输出目录不能是原文件所在目录，以免派生目标与原文件重合。

需要重新生成已有输出时加入：

```powershell
--overwrite
```

需要显式指定 FFmpeg 时加入：

```powershell
--ffmpeg 'C:\路径\ffmpeg.exe'
```

## 输入与输出

`--source` 可以是一个媒体文件，也可以是目录。目录模式会递归扫描 MP3、WAV、
FLAC、M4A、AAC、OGG、OPUS、WMA，以及包含音轨的 MP4、FLV、MKV、MOV 和
WEBM，并将结果平铺到输出目录：

```text
music/
├── 歌曲A.mp3
├── 歌曲A.lrc
└── 歌曲B.mp3
```

- 音频统一为 44.1 kHz、双声道、320 kbps MP3。
- 视频文件固定提取第一条音轨，忽略视频、字幕和数据流；没有音轨时将该文件报告为失败。
- 使用两遍 FFmpeg `loudnorm`，目标约为 `-16 LUFS`、`-1.5 dBTP`。
- 输出 MP3 不继承输入文件的 ID3、XMP、封面等元数据，避免编辑软件写入的私有标签影响 Windows 播放兼容性。
- 同名 LRC 会统一转为 UTF-8；没有 LRC 时仍然输出歌曲。
- 输出文件名保留原名主体，并清理 Windows 非法字符；重名时追加 ` (2)`、` (3)`。
- 输出目录是扁平结构，不保留源目录层级。
- 原始文件永远不会被修改、移动或删除。
- 默认跳过已有输出；`--overwrite` 只覆盖输出目录中的派生文件。
- 源目录和输出目录不能相同，也不能互相包含。

处理完成后会在输出目录生成 `prepare_music_report.txt`。单首歌曲失败不会阻止其他歌曲继续处理。

如果提示“无法解码源文件”，说明 FFmpeg 读到文件末尾仍无法确定音频格式，
尚未完成响度分析。请检查原文件是否损坏、扩展名是否与实际格式一致，或是否为
下载软件的加密文件；需从来源软件导出标准音频，直接改为 `.flac` 或 `.mp3`
不能转换格式。报告会保留 FFmpeg 的主要错误原因。

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
$whisperRoot = Join-Path $PWD 'release-v1.0\tools\whisper'
New-Item -ItemType Directory -Path $whisperRoot -Force | Out-Null
curl.exe --fail --location --progress-bar `
  'https://github.com/ggml-org/whisper.cpp/releases/download/v1.9.1/whisper-cublas-12.4.0-bin-x64.zip' `
  --output (Join-Path $whisperRoot 'whisper-cuda.zip')
Expand-Archive -LiteralPath (Join-Path $whisperRoot 'whisper-cuda.zip') `
  -DestinationPath $whisperRoot -Force
```

下载识别质量优先的完整 `large-v3` 模型，约 3.1 GB；命令支持中断后继续下载：

```powershell
$modelRoot = Join-Path $PWD 'release-v1.0\tools\whisper\models'
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
$modelRoot = Join-Path $PWD 'release-v1.0\tools\whisper\models'
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

- 不整理或保留 ID3 标题、歌手、封面等元数据；预处理输出会移除输入元数据以保证播放兼容性。
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

播放器固定读取 `OnScreenMusic.exe` 旁边 `playlists` 目录中的 UTF-8 `.txt` 歌单，音乐和歌词分别放在 `music`、`lyrics`。这些子目录须已经存在，程序不会创建、移动或复制资料。开发构建后，目录类似：

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
| `Library/PlaylistFile` | 当前歌单文件名 |
| `Playback/AudioFile` | 当前音乐文件名 |
| `Playback/PositionMs` | 当前播放位置，单位为毫秒 |
| `Playback/SingleRepeat` | 单曲循环开关；缺省为关闭，切换时保存并在启动时恢复 |
| `Audio/Volume` | 主音量 |
| `Window/Position` | 歌词窗口屏幕坐标 |

托盘“音乐管理”打开独立管理界面。两部分固定读取同目录的 `playlists`、`music`、`lyrics`；保存歌词或歌单后，在播放器点击“刷新”即可重读。

播放期间约每两秒保存一次，并在暂停、跳转播放点、切歌、切换歌单、调节音量、移动窗口和正常退出时保存。程序启动后恢复这些值，但仍保持暂停和未隐藏。移动程序时应把整个软件目录一起移动，包括 INI、三个资料子目录、工作目录以及 Whisper 程序和模型。

如果要完全重置播放器，应先退出程序，再删除 `OnScreenMusic.ini`。运行时通过音乐管理设置页修改配置；手工编辑前先关闭两部分程序。重置统一 INI 也会清除工具路径和 API 配置，请先保留所需信息。

纯音乐即使在歌单中配置了 LRC，也可以在该 LRC 第一行写入：

```text
#INSTRUMENTAL
```

程序会忽略标记的大小写、UTF-8 BOM 和首尾空格。检测到标记后不再解析后续歌词，整首只在歌词区域居中显示 `_`；标记必须位于文件第一行。没有配对歌词、歌词文件缺失或没有有效歌词的歌曲，以及有效歌词开始前，也统一显示 `_`，不再把歌曲名放在主歌词区域。每句歌词最多显示 5 秒；距离该句时间戳达到 5 秒且尚未进入下一句时显示 `_`，最后一句也会在 5 秒后变为 `_`。

歌词层每次启动都默认解锁，可以直接点击按钮、拖动进度和拖动窗口。未隐藏时，在歌词层任意位置（包括按钮、进度条和文字）按住鼠标中键都能移动整个窗口，松开后保存位置；隐藏穿透时需先通过快捷键或托盘恢复。歌词始终保持单行，不会自动换行或撑高悬浮层；短歌词使用最大 60 px 字号，较长歌词会自动选择能够完整放入当前宽度的最大字号。点击“隐藏”后会透明化控件并让整个歌词层鼠标穿透，同时保留控制条的布局空间，因此歌词位置不会变化；隐藏状态不会跨启动保存。所有控制按钮尺寸相同，歌词靠近下方进度条显示，最右侧“关闭”按钮会直接退出程序。程序会保存歌单、歌曲、播放点、窗口位置和音量。选歌按钮会打开带搜索框的歌曲列表，选歌单按钮会打开临时歌单列表，`🔊` 会打开小型音量滑块，音量范围限制为 Qt 原始音量的 0–20%。

“选歌单”后的单曲循环按钮显示 `↻×`（关闭）或 `↻1`（开启），点击切换，按钮尺寸与其他控制按钮相同。首次使用默认关闭；切换时保存到 EXE 旁的 `OnScreenMusic.ini`，重新启动恢复上次的开关状态和按钮文字。开启后，点击下一首、按 `左Ctrl+Num4` 或歌曲自然结束，都会从头重播当前歌曲；关闭后恢复原来的随机切歌。手动选歌或切换歌单仍可选择其他歌曲，循环开关保持当前状态。

进度条支持点击任意位置直接跳转，也可以按住滑块拖动。“刷新”按钮会重新扫描 `playlists` 并重读当前歌单和当前歌曲的 LRC：当前歌曲仍有效时保持播放/暂停状态和播放点；歌曲已被移除或变成无效配置时，从刷新后的歌单随机载入一首并保持暂停。刷新只在点击按钮时执行，不进行后台文件轮询。

固定全局快捷键：

- `左Ctrl+Num5`：播放/暂停。
- `左Ctrl+Num4`：下一首。
- `左Ctrl+Num6`：隐藏或恢复歌词层控件。
- `左Ctrl+Num1`：回退 5 秒。
- `左Ctrl+Num3`：快进 5 秒。

快捷键通过 Windows Raw Input 在后台接收左 Ctrl 和数字小键盘 1/3/4/5/6 的物理扫描码，NumLock 开启或关闭都可使用，同时不会占用主键盘的方向键；右 Ctrl 不参与播放器快捷键，也不提供音量和选歌全局快捷键。按键处理完全由事件驱动，不进行持续轮询，也不会吞掉按键，因此播放器和当前游戏可能同时响应同一组合键。Num1、Num3、Num4 按下时立即执行一次，持续按住 500 ms 后开始重复；Num1/Num3 每 200 ms 重复，Num4 每 700 ms 重复。Num5 和 Num6 长按不重复。释放数字键或左 Ctrl 后，当前重复立即停止。快进和回退会限制在 `00:00` 与歌曲总时长之间，暂停时跳转后仍然保持暂停。

系统托盘最上方显示当前快捷键模式：默认的“全部快捷”表示五组快捷键均启用；点击后变为“播放专用”，此时播放器仅响应 `左Ctrl+Num5`，忽略其余四组。再次点击恢复全部快捷键。该模式每次启动默认关闭且不保存，也不显示勾选标记。切换模式会停止正在进行的长按操作。托盘“音乐管理”打开同目录的 Music Workshop；其余项目为“锁定窗口/解锁窗口”、“隐藏窗口/显示窗口”、“软件说明”和“退出软件”。“软件说明”显示 On Screen Music v1.0、制作时间、制作者及上述基本用法，不联网，也不检查更新。

若物理小键盘快捷键初始化失败，系统托盘会提示，其他功能不受影响。
