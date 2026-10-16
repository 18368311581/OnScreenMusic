#!/usr/bin/env python3
"""Standalone entry point; no imports from the On Screen Music player."""
import sys
from pathlib import Path

if __name__ == "__main__" and len(sys.argv) > 2 and sys.argv[1] == "--workshop-tool":
    import runpy
    module = sys.argv[2]
    if module not in {"workshop.worker", "workshop.tool_setup"}:
        raise SystemExit("Unknown background command")
    sys.argv = [module, *sys.argv[3:]]
    runpy.run_module(module, run_name="__main__")
    raise SystemExit(0)

if __name__ == "__main__" and len(sys.argv) == 4 and sys.argv[1] == "--startup-probe":
    from tools.benchmark_workshop_startup import child
    raise SystemExit(child(Path(sys.argv[2]), Path(sys.argv[3])))

if sys.version_info < (3, 12):
    import ctypes
    ctypes.windll.user32.MessageBoxW(None, "请使用 Python 3.12，或双击同目录的 MusicWorkshop.vbs。", "Music Workshop", 48)
    raise SystemExit(2)

try:
    from workshop.gui import main
except ModuleNotFoundError as exc:
    if exc.name and exc.name.startswith(("PySide6", "shiboken6")):
        import ctypes
        ctypes.windll.user32.MessageBoxW(None,
            "此 Python 环境缺少 PySide6。请使用已配置 PySide6 的 Python 3.12，或双击 MusicWorkshop.vbs。",
            "音乐管理启动失败", 48)
        raise SystemExit(2)
    raise

if __name__ == "__main__":
    raise SystemExit(main())
