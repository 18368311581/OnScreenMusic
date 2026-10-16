# On Screen Music 1.1.0

本次更新为 On Screen Music 新增附属的音乐管理工具 MusicWorkshop，可从播放器托盘打开。播放器与管理工具同目录部署、分别运行，随整套软件统一发布。

新增歌曲预处理、本地歌词识别、参考歌词 AI 校对、歌词直接编辑和内置试听、歌单权重与检查、逐项任务终止、工具下载、临时文件清理和深浅色样式。

识别或校对整项成功后，最终歌词会自动写入对应 LRC，旧版先备份；失败或终止保留原歌词。原始音频不修改、不删除。新素材转换出的 MP3 保存在工作目录，整理后放入资料库。

## 下载

- `OnScreenMusic-1.1.0-windows-x64.zip`：完整便携软件，解压即用，无需另装 Python。
- `OnScreenMusic-1.1.0-source.zip`：本版本源码、图标、测试与构建脚本。
- `OnScreenMusic-1.1.0-third-party-sources.zip`：第三方对应源码归档、版本与来源清单。
- `SHA256SUMS.txt`：上述文件的 SHA-256 校验值。

保留软件目录结构；不要只复制某个 EXE。下载包不包含个人配置、歌曲、歌词、模型、密钥或任务记录。首次使用可在参数设置中下载或选择 FFmpeg、识别程序与模型，large-v3 模型约 3.1 GB。

## 升级

先关闭播放器、音乐管理和下载窗口，备份自己的资料。将新程序解压到新目录，再迁入 `OnScreenMusic.ini`、`music`、`lyrics`、`playlists` 和需要保留的 `MusicWorkshopWork`。同目录 `tools` 可一起迁入，已有模型无需重新下载。不要把资料迁入 `MusicWorkshopRuntime`。

## 验证范围

播放器 Release / Debug 已完成本机全新影子构建。Python 测试共 161 项，160 项通过，1 项因 Windows 符号链接权限跳过。AI 请求使用模拟响应，实际内容质量由使用者确认。

已完成本机打包与入口验证；尚未完成其他电脑验收，不保证所有 Windows 环境的音频后端、快捷键或启动速度与开发机相同。

原创代码与资源采用 MIT；Qt、PySide6 等组件遵守各自许可。完整许可与对应源码说明随包提供，详见 `ThirdPartyNotices`。
