# Build a windowed UI and a console worker sharing one directory of dependencies.
from pathlib import Path
import os
import sys
from PyInstaller.utils.win32.versioninfo import VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable, StringStruct, VarFileInfo, VarStruct

root = Path(SPECPATH).parent
# Keep unrelated developer-tool DLLs out of the bundle's dependency search.
windows = Path(os.environ['SystemRoot'])
os.environ['PATH'] = os.pathsep.join(map(str, [Path(sys.base_prefix), windows / 'System32', windows]))
product_version = (root / 'VERSION').read_text(encoding='utf-8').strip()
version_tuple = tuple(map(int, product_version.split('.'))) + (0,)
version = VSVersionInfo(
    ffi=FixedFileInfo(filevers=version_tuple, prodvers=version_tuple, mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0, 0)),
    kids=[StringFileInfo([StringTable('080404B0', [
        StringStruct('CompanyName', 'Inseven'), StringStruct('FileDescription', 'On Screen Music 音乐管理'),
        StringStruct('FileVersion', product_version), StringStruct('ProductName', 'On Screen Music'),
        StringStruct('ProductVersion', product_version)])]), VarFileInfo([VarStruct('Translation', [2052, 1200])])])
a = Analysis([str(root / 'MusicWorkshop.pyw')], pathex=[str(root)],
    binaries=[], datas=[(str(root / 'workshop/icons'), 'workshop/icons'), (str(root / 'VERSION'), '.')],
    hiddenimports=['workshop.worker', 'workshop.tool_setup', 'workshop.maintenance', 'tools.benchmark_workshop_startup'],
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=['tkinter'], noarchive=False)
pyz = PYZ(a.pure)
gui = EXE(pyz, a.scripts, [], exclude_binaries=True, name='MusicWorkshop', console=False,
    debug=False, strip=False, upx=False, icon=str(root / 'workshop/icons/workshop.ico'),
    version=version, contents_directory='MusicWorkshopRuntime')
worker = EXE(pyz, a.scripts, [], exclude_binaries=True, name='MusicWorkshopTool', console=True,
    debug=False, strip=False, upx=False, icon=str(root / 'workshop/icons/workshop.ico'),
    version=version, contents_directory='MusicWorkshopRuntime')
coll = COLLECT(gui, worker, a.binaries, a.datas, strip=False, upx=False, name='MusicWorkshop')
