"""Create audited binary/source/source-dependency archives and a Git staging allowlist."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = ['.gitignore','.gitattributes','AGENTS.md','README.md','LICENSE','CHANGELOG.md','VERSION',
              'on_screen_music.pro','resources.qrc','MusicWorkshop.pyw','MusicWorkshop.vbs',
              'requirements-workshop.txt','requirements-build.txt']
SOURCE_TYPES = {'.py','.pyw','.ps1','.spec','.cpp','.h','.svg','.ico','.png','.md','.txt','.json','.yml','.yaml'}
SECRET_PATTERNS = {'API token': re.compile(rb'\bsk-[A-Za-z0-9_-]{24,}\b'),
                   'GitHub token': re.compile(rb'\bgh[pousr]_[A-Za-z0-9]{25,}\b')}


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source,'sha256').hexdigest()


def source_files():
    result = [ROOT/name for name in ROOT_FILES]
    for folder in ['src','workshop','tools','tests','assets','docs','licenses','.github']:
        for path in (ROOT/folder).rglob('*'):
            relative = path.relative_to(ROOT)
            if not path.is_file() or path.is_symlink() or '__pycache__' in path.parts:
                continue
            if any(part in {'whisper','.packaging-venv','.third-party-cache','node_modules'} for part in relative.parts):
                continue
            if folder == 'tools' and (len(relative.parts) != 2 or path.suffix.lower() not in {'.py','.pyw','.ps1','.spec'}):
                continue
            if folder == 'tests' and path.suffix.lower() not in {'.py','.cpp','.h'}:
                continue
            if path.name.endswith(('_report.txt','.local.ini')):
                continue
            if folder == 'licenses' or path.suffix.lower() in SOURCE_TYPES:
                result.append(path)
    return sorted(set(result), key=lambda path:path.relative_to(ROOT).as_posix())


def write_zip(target, files, prefix, base, compression=zipfile.ZIP_DEFLATED):
    if target.exists():
        raise FileExistsError('Release output already exists: '+str(target))
    with zipfile.ZipFile(target,'w',compression=compression,compresslevel=6 if compression == zipfile.ZIP_DEFLATED else None) as output:
        for path in files:
            output.write(path,prefix+'/'+path.relative_to(base).as_posix())
        for folder in ('music','lyrics','playlists') if base.name.endswith('-windows-x64') else ():
            output.writestr(prefix+'/'+folder+'/',b'')


def main():
    version = (ROOT/'VERSION').read_text(encoding='utf-8').strip()
    output = ROOT/'packages'
    binary = output/f'OnScreenMusic-{version}-windows-x64'
    source = source_files()
    for path in source:
        if not path.is_file():
            raise FileNotFoundError(path)
        if path.stat().st_size > 5*1024**2:
            raise ValueError('Unexpected large source file: '+str(path.relative_to(ROOT)))
        if path.suffix.lower() not in {'.png','.ico'}:
            content = path.read_bytes()
            for label, pattern in SECRET_PATTERNS.items():
                if pattern.search(content):
                    raise ValueError(label+' detected; review '+str(path.relative_to(ROOT)))
    forbidden = {'OnScreenMusic.ini','jobs.json','debug.log'}
    binary_files = sorted(path for path in binary.rglob('*') if path.is_file())
    for path in binary_files:
        if path.name in forbidden or path.suffix.lower() in {'.mp3','.lrc'} or path.name.startswith('ggml-'):
            raise ValueError('Private/runtime data in release: '+str(path.relative_to(binary)))
    for folder in ('music','lyrics','playlists'):
        if not (binary/folder).is_dir() or any((binary/folder).iterdir()):
            raise ValueError('Release media directories must exist and be empty.')
    source_manifest = [{'path':path.relative_to(ROOT).as_posix(),'sha256':digest(path),'bytes':path.stat().st_size} for path in source]
    (output/f'OnScreenMusic-{version}-source-manifest.json').write_text(json.dumps(source_manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    work = ROOT/'build-workshop';work.mkdir(exist_ok=True)
    (work/'publication-files.nul').write_bytes(b''.join(path.relative_to(ROOT).as_posix().encode('utf-8')+b'\0' for path in source))
    artifacts = []
    target = output/f'OnScreenMusic-{version}-windows-x64.zip'
    write_zip(target,binary_files,binary.name,binary)
    artifacts.append(target)
    target = output/f'OnScreenMusic-{version}-source.zip'
    write_zip(target,source,f'OnScreenMusic-{version}-source',ROOT)
    artifacts.append(target)
    records = json.loads((ROOT/'licenses/SOURCES.json').read_text(encoding='utf-8'))
    target = output/f'OnScreenMusic-{version}-third-party-sources.zip'
    if target.exists():
        raise FileExistsError(target)
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_STORED) as bundle:
        bundle.write(ROOT/'licenses/SOURCES.json','SOURCES.json')
        bundle.write(ROOT/'licenses/THIRD_PARTY.md','THIRD_PARTY.md')
        for row in records:
            archive = ROOT/'.third-party-cache'/row['archive']
            if digest(archive) != row['sha256']:
                raise ValueError('Third-party source checksum changed: '+row['archive'])
            bundle.write(archive,'archives/'+archive.name)
    artifacts.append(target)
    manifest = output/f'OnScreenMusic-{version}-source-manifest.json'
    artifacts.append(manifest)
    (output/'SHA256SUMS.txt').write_text(''.join(digest(path)+'  '+path.name+'\n' for path in artifacts),encoding='utf-8')
    for path in artifacts:
        with zipfile.ZipFile(path) if path.suffix == '.zip' else open(path,'rb') as check:
            if isinstance(check,zipfile.ZipFile) and check.testzip() is not None:
                raise ValueError('Archive verification failed: '+path.name)
    print('Release artifacts prepared:',version,'source files:',len(source))
    for path in artifacts:
        print(path.name, path.stat().st_size)


if __name__ == '__main__':
    main()
