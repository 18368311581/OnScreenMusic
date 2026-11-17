# On Screen Music 1.1.1

新增 **左 Ctrl + 小键盘 2**，隐藏或显示整个播放器窗口，与托盘菜单功能一致。左 Ctrl + 小键盘 6 仍控制歌词层控件和鼠标穿透。“播放专用”模式仅响应左 Ctrl + 小键盘 5。

## 下载与升级

- `OnScreenMusic-1.1.1-windows-x64.zip`：Windows x64 便携软件，请保留完整目录结构。
- `OnScreenMusic-1.1.1-source.zip`：源码、测试和构建脚本。
- `OnScreenMusic-1.1.1-third-party-sources.zip`：第三方源码归档及来源清单。
- `SHA256SUMS.txt`：文件校验值。

升级前关闭播放器、音乐管理和下载窗口并备份资料；将新版本解压到新目录，再迁入 `OnScreenMusic.ini`、`music`、`lyrics`、`playlists` 和需要保留的 `MusicWorkshopWork`。已有工具和模型可随 `tools` 迁入，不要放入 `MusicWorkshopRuntime`。发行包不含个人配置、歌曲、歌词、密钥或模型。

## 验证范围

已在开发者电脑构建并运行自动化检查。物理快捷键、真实媒体行为及其他电脑的运行效果尚需人工验收。AI 校对和识别质量取决于实际输入与服务。

原创代码与资源采用 MIT；Qt、PySide6 等组件遵守各自许可，详见包内 `ThirdPartyNotices`。
