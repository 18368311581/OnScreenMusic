# 第三方组件、许可与对应源码

On Screen Music 的原创代码和资源采用 MIT。下列组件遵守各自许可；项目 MIT 许可证不替代第三方条款。

## 实际使用的主要组件

| 组件 | 版本 | 本发行包中的用途与许可选择 |
| --- | --- | --- |
| Qt 5 qtbase / qtmultimedia | 5.14.0 | 播放器共享库和插件；采用 LGPLv3 选项 |
| Qt 6 qtbase / qtsvg / qtimageformats | 6.11.2 | 音乐管理的共享库、界面与图像插件；采用 LGPLv3 选项 |
| PySide6 Essentials / Shiboken runtime | 6.11.2 | Python 绑定；采用 LGPLv3 选项 |
| CPython | 3.12.2 | Python 运行时；PSF 许可及其中的第三方声明 |
| PyInstaller bootloader | 6.22.3 | 启动入口；GPLv2 与其分发例外，见原始 COPYING |
| GCC runtime | 7.3.0 | libgcc / libstdc++；GPLv3 与 GCC Runtime Library Exception |
| MinGW-w64 / winpthreads | 6.0.0 | Windows 运行库；原始许可与版权见配套声明 |
| OpenSSL | 3.0.13 | Python HTTPS；Apache-2.0 |
| zlib | 1.3.1 | 压缩；zlib 许可 |
| Expat | 2.5.0 | XML；MIT 许可 |
| libffi | 3.4.4 | ctypes；MIT 类许可 |

Qt 自身还包含第三方实现，例如图像、字体、压缩与文本处理代码。原始的 `qt_attribution.json` 和许可文本保存在 `third-party` 子目录中，完整对应源码在下面的归档中。上游源码归档可能包含本发行包未启用的模块、测试或工具；保留这些上游声明不表示软件分发了所有对应代码。

Python、Qt 的原始分发包含 Microsoft Visual C++ 运行时 DLL；其所有权和分发条款仍归 Microsoft。未将 Windows 自带系统库或 SDK 作为本项目源码重新授权。

## 对应源码的获取

每次发行同时提供 `OnScreenMusic-<版本>-third-party-sources.zip`。它包含本次使用的固定版本上游源码归档，以及 `SOURCES.json`（下载地址、版本、归档名与 SHA-256）。项目自身源码另有同版本的 `source.zip`。

请从同一 [GitHub Release](https://github.com/18368311581/OnScreenMusic/releases) 获取这两类源码附件。若从其他下载平台分发，请保留本说明，并同时提供这些源码附件的获取入口；不要只转载 EXE 或删掉第三方许可文件。

源码仓库中的 `tools/prepare_third_party.py` 可以按同样的版本与地址重新获取。缓存不加入 Git；正式发布时，归档清单与本文件所述版本须一致。

## 修改共享库与重新构建

本软件动态使用 Qt 和 Python 绑定，未对库施加签名锁定或校验阻止替换。可以使用接口兼容的修改版共享库，或用项目的公开源码重新构建；安装与重建步骤见 `docs/BUILDING.md`。

用户依适用第三方许可享有的权利不受项目 MIT 许可证或使用说明限制，包括为调试这些库的修改而进行必要的逆向工程。

## 原始声明

发行包 `ThirdPartyNotices` 包含本说明、原始许可文本、组件及源码清单。Qt / PySide6 / Shiboken 的商业许可文本是上游提供的另一种选择，本软件采用上表所述开源选项，不要求使用者购买商业许可。

官方参考：[Qt 开源义务](https://www.qt.io/development/open-source-lgpl-obligations)、[Qt 第三方组件](https://doc.qt.io/qt-6/licenses-used-in-qt.html)、[Qt for Python 许可](https://doc.qt.io/qtforpython-6/licenses.html)。
