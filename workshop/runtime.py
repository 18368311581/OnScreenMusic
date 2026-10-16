"""Launch paths shared by source and directory-bundled editions."""
from pathlib import Path
import sys


def application_root():
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]


def tool_command(module, *arguments):
    if module not in {"workshop.worker", "workshop.tool_setup"}:
        raise ValueError("未知后台程序。")
    if getattr(sys, "frozen", False):
        executable = application_root() / "MusicWorkshopTool.exe"
        if not executable.is_file():
            raise FileNotFoundError("后台程序文件缺失，请重新解压完整的软件目录。")
        return [str(executable), "--workshop-tool", module, *map(str, arguments)]
    executable = Path(sys.executable)
    if executable.name.casefold() == "pythonw.exe":
        executable = executable.with_name("python.exe")
    return [str(executable), "-u", "-m", module, *map(str, arguments)]
