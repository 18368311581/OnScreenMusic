"""Collect upstream license texts and corresponding-source metadata into a release."""
import argparse
import importlib.metadata
from pathlib import Path
import shutil
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('destination', type=Path)
    parser.add_argument('--qt-directory', type=Path, default=Path('D:/Qt/Qt5.14.0/5.14.0/mingw73_64'))
    parser.add_argument('--mingw-directory', type=Path, default=Path('D:/Qt/Qt5.14.0/Tools/mingw730_64'))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if not (root/'licenses/SOURCES.json').is_file():
        raise SystemExit('Run tools/prepare_third_party.py first to prepare original notices and source manifests.')
    target = args.destination / 'ThirdPartyNotices'
    target.mkdir(parents=True, exist_ok=True)
    rows = ['On Screen Music '+(root/'VERSION').read_text(encoding='utf-8').strip(),
            'Qt / PySide6 / Shiboken copyright The Qt Company Ltd. and contributors.',
            'This application uses the LGPLv3 options for the Qt libraries and Python binding runtime.',
            'See THIRD_PARTY.md, SOURCES.json and Upstream for notices, full license texts and corresponding source archives.',
            '', f'Python {sys.version.split()[0]}']
    shutil.copy2(root/'licenses/THIRD_PARTY.md', target/'THIRD_PARTY.md')
    shutil.copy2(root/'licenses/SOURCES.json', target/'SOURCES.json')
    shutil.copytree(root/'licenses/third-party', target/'Upstream', dirs_exist_ok=True)
    for folder in ('gcc','mingw-w64','winpthreads'):
        shutil.copytree(args.mingw_directory/'licenses'/folder, target/'MinGW'/folder, dirs_exist_ok=True)
    python_license = Path(sys.base_prefix) / 'LICENSE.txt'
    if python_license.exists():
        shutil.copy2(python_license, target / 'Python-LICENSE.txt')
    for name in ('PySide6_Essentials', 'shiboken6', 'PyInstaller'):
        distribution = importlib.metadata.distribution(name)
        rows.extend(['', name + ' ' + distribution.version, 'License metadata: ' + (distribution.metadata.get('License') or 'See bundled license file')])
        for entry in distribution.files or []:
            if '/licenses/' in str(entry).replace('\\', '/'):
                source = distribution.locate_file(entry)
                if source.is_file():
                    destination = target / name / Path(str(entry).split('/licenses/', 1)[1])
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
    rows.extend(['', 'The player also includes Qt 5.14.0 runtime and MinGW 7.3 / MinGW-w64 6.0 runtime DLLs.',
                 'Qt license reference: https://doc.qt.io/qt-5/licensing.html',
                 'Qt for Python license reference: https://doc.qt.io/qtforpython-6/licenses.html',
                 'FFmpeg, Whisper and models are not included.'])
    (target / 'Components.txt').write_text('\n'.join(rows) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
