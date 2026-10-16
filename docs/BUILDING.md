# 从源码构建

整套产品使用根目录 `VERSION`，播放器与附属工具统一发布，不单独维护 MusicWorkshop 对外版本。

## 工具链

- Windows x64、PowerShell 7。
- 播放器：Qt 5.14.0 Widgets / Multimedia、MinGW 7.3 64 位、qmake、C++17。
- 音乐管理：Python 3.12、PySide6-Essentials 6.11.2。
- 目录式打包：PyInstaller 6.22.3。运行包无需用户另装 Python。

```powershell
python -m venv .packaging-venv
& .\.packaging-venv\Scripts\python.exe -m pip install -r requirements-build.txt
pwsh -File .\tools\build_player.ps1 -Configuration Release
```

Qt 与 MinGW 路径可通过 `-QtDirectory`、`-MinGWDirectory` 指定。脚本只改变当前进程的 PATH。调试构建将配置改为 `Debug`。

## 源码直接运行

创建已有的空 `music`、`lyrics`、`playlists` 资料目录后，用 Python 运行 `MusicWorkshop.pyw`。本机源码入口在存在 `release-v1.0/OnScreenMusic.exe` 时沿用该历史运行目录的资料；目录名不代表当前版本。不要把自己的资料提交到仓库。

## 生成发行包

```powershell
& .\.packaging-venv\Scripts\python.exe -B tools/prepare_third_party.py
pwsh -File .\tools\package_workshop.ps1 -PlayerExe .\build-release\OnScreenMusic.exe
& .\.packaging-venv\Scripts\python.exe -B tools/prepare_release.py
```

许可收集读取本机 Qt SDK 的许可材料，并缓存固定版本的第三方源码归档。归档位于被忽略的 `.third-party-cache`；对应下载地址与 SHA-256 清单随发行材料提供，不把归档加入 Git。官方源码不执行。

`package_workshop.ps1` 使用独立运行目录和明确文件清单，不包含本机配置、歌曲、歌词、模型、任务记录或备份。源码分发同样使用白名单，排除开发环境、输出目录及 Qt Creator 私有文件。

## 验证与测量

```powershell
& .\.packaging-venv\Scripts\python.exe -B -X utf8 -m unittest discover -s tests
python -B tools/benchmark_workshop_startup.py --root .\release-v1.0 --runs 5
python -B tools/benchmark_workshop_startup.py --root .\release-v1.0 --executable .\dist-workshop\MusicWorkshop\MusicWorkshop.exe --runs 5
```

测试只使用临时媒体目录，在线 AI 使用模拟响应。启动测量从进程创建到首次窗口绘制，不等同于冷开机后的启动保证。其他电脑验收暂未完成，不将本机构建或模拟测试表述为跨电脑验收。

## 第三方替换与重新链接

播放器动态加载根目录 Qt 5 DLL；音乐管理动态加载 `MusicWorkshopRuntime/PySide6` 的 Qt 6 DLL 和绑定。可在保留许可证并遵守对应条款的情况下，使用接口兼容的修改版本替换这些共享库，或按上述工具链重建。项目不禁止为调试第三方库修改而进行必要的逆向工程。

第三方源码位置、版本、归档与许可见 `licenses/THIRD_PARTY.md`。项目 MIT 许可证不替代各第三方的许可证。
