"""Cache exact-version upstream source archives and extract their original license notices."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [
    ('Qt5-qtbase','5.14.0','https://codeload.github.com/qt/qtbase/tar.gz/refs/tags/v5.14.0'),
    ('Qt5-qtmultimedia','5.14.0','https://codeload.github.com/qt/qtmultimedia/tar.gz/refs/tags/v5.14.0'),
    ('Qt6-qtbase','6.11.2','https://codeload.github.com/qt/qtbase/tar.gz/refs/tags/v6.11.2'),
    ('Qt6-qtsvg','6.11.2','https://codeload.github.com/qt/qtsvg/tar.gz/refs/tags/v6.11.2'),
    ('Qt6-qtimageformats','6.11.2','https://codeload.github.com/qt/qtimageformats/tar.gz/refs/tags/v6.11.2'),
    ('PySide-Shiboken','6.11.2','https://codeload.github.com/pyside/pyside-setup/tar.gz/refs/tags/v6.11.2'),
    ('CPython','3.12.2','https://codeload.github.com/python/cpython/tar.gz/refs/tags/v3.12.2'),
    ('PyInstaller','6.22.3','https://codeload.github.com/pyinstaller/pyinstaller/tar.gz/refs/tags/v6.22.3'),
    ('OpenSSL','3.0.13','https://codeload.github.com/openssl/openssl/tar.gz/refs/tags/openssl-3.0.13'),
    ('zlib','1.3.1','https://codeload.github.com/madler/zlib/tar.gz/refs/tags/v1.3.1'),
    ('libexpat','2.5.0','https://codeload.github.com/libexpat/libexpat/tar.gz/refs/tags/R_2_5_0'),
    ('libffi','3.4.4','https://codeload.github.com/libffi/libffi/tar.gz/refs/tags/v3.4.4'),
    ('GCC-runtime','7.3.0','https://ftp.gnu.org/gnu/gcc/gcc-7.3.0/gcc-7.3.0.tar.xz'),
    ('MinGW-w64','6.0.0','https://codeload.github.com/mingw-w64/mingw-w64/tar.gz/refs/tags/v6.0.0'),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cache', type=Path, default=ROOT / '.third-party-cache')
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    notices = ROOT / 'licenses/third-party'
    notices.mkdir(parents=True, exist_ok=True)
    manifest = []
    downloaded = 0
    for name, version, url in SOURCES:
        extension = '.tar.xz' if url.endswith('.xz') else '.tar.gz'
        archive = args.cache / (name + '-' + version + extension)
        if not archive.exists():
            print('Downloading upstream source:', name, version, flush=True)
            temporary = archive.with_name(archive.name + '.part')
            request = urllib.request.Request(url, headers={'User-Agent':'OnScreenMusic-release-preparation'})
            with urllib.request.urlopen(request, timeout=60) as response, temporary.open('wb') as output:
                count = 0
                while data := response.read(1024**2):
                    count += len(data)
                    downloaded += len(data)
                    if count > 250*1024**2 or downloaded > 900*1024**2:
                        raise ValueError('Source downloads exceeded the expected budget; stopped before GB-scale content.')
                    output.write(data)
            if not tarfile.is_tarfile(temporary):
                raise ValueError('The upstream response is not a source archive: ' + name)
            temporary.replace(archive)
        with archive.open('rb') as source:
            digest = hashlib.file_digest(source, 'sha256').hexdigest()
        count = 0
        with tarfile.open(archive) as source:
            for member in source:
                path = PurePosixPath(member.name)
                lower = path.name.lower()
                if (not member.isfile() or member.size > 2*1024**2 or path.is_absolute() or '..' in path.parts
                        or len(path.parts) < 2):
                    continue
                if not (any(word in lower for word in ('license','copying','copyright','notice'))
                        or lower in {'qt_attribution.json','ftl.txt'}):
                    continue
                relative = Path(*path.parts[1:])
                target = notices / name / relative
                if not target.resolve().is_relative_to((notices/name).resolve()):
                    raise ValueError('Unsafe notice path')
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.extractfile(member) as data:
                    target.write_bytes(data.read())
                count += 1
        manifest.append({'component':name,'version':version,'url':url,'archive':archive.name,
                         'sha256':digest,'bytes':archive.stat().st_size,'notice_files':count})
        print(name, version, 'notices:', count, flush=True)
    (ROOT/'licenses/SOURCES.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print('Exact-version source archives and original notices prepared.', flush=True)


if __name__ == '__main__':
    main()
