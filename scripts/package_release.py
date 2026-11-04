"""Package native binaries, clean Python source and dependency notices."""
from pathlib import Path
import argparse
import importlib.metadata
import shutil
import zipfile

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'release-native'


def source_files(root=ROOT):
    """Enumerate public source; private fonts and reference originals never ship."""
    files = []
    for name in ('app', 'assets', 'scripts', 'tests', 'docs'):
        for p in (root / name).rglob('*'):
            if not p.is_file() or '__pycache__' in p.parts or p.suffix in ('.pyc',) or p.name == '工作台预览.jpg':
                continue
            relative = p.relative_to(root)
            if relative.parts[:2] in (('assets', 'fonts'), ('assets', 'reference')) and p.name != 'README.md':
                continue
            files.append((p, str(Path('归档-Python源码') / relative)))
    for name in ('main.py', 'requirements.txt', 'requirements-build.txt', 'requirements-lock.txt', 'README.md', 'RELEASE_NOTES.md', 'THIRD_PARTY_NOTICES.md', 'LICENSE', '.gitignore', '.gitattributes', '运行源码.cmd'):
        files.append((root / name, '归档-Python源码/' + name))
    return files


def make_archive(destination, files):
    temporary = destination.with_suffix(destination.suffix + '.tmp')
    try:
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path, name in files:
                archive.write(path, Path(name).as_posix())
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description='Package a native Windows release and Python sources.')
    parser.add_argument('--format', choices=['directory', 'singlefile', 'source'], default='directory')
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True)
    folder = OUT / '归档'
    if args.format == 'directory':
        if not (folder / '归档.exe').is_file():
            raise RuntimeError('Build the native directory executable first.')
        shutil.copyfile(ROOT / 'docs/使用说明.md', folder / '使用说明.md')
        shutil.copyfile(ROOT / 'THIRD_PARTY_NOTICES.md', folder / 'THIRD_PARTY_NOTICES.md')
        shutil.copyfile(ROOT / 'LICENSE', folder / 'LICENSE')
        licenses = folder / 'licenses'
        licenses.mkdir(exist_ok=True)
        for text in (ROOT / 'assets/licenses').glob('*'):
            if text.is_file():
                shutil.copyfile(text, licenses / text.name)
        for package in ('PySide6-Essentials', 'shiboken6', 'lxml'):
            dist = importlib.metadata.distribution(package)
            for file in dist.files or []:
                path = Path(str(file))
                if ('license' in str(path).lower() or path.name.lower().startswith('copying')) and path.suffix.lower() in ('.txt', '.rst', '.md', ''):
                    source = Path(dist.locate_file(file))
                    if source.is_file():
                        shutil.copyfile(source, licenses / (package + '-' + path.name))
        make_archive(OUT / '归档-Windows原生桌面版.zip', [(p, str(Path('归档') / p.relative_to(folder))) for p in folder.rglob('*') if p.is_file()])
    elif args.format == 'singlefile':
        if not (OUT / '归档.exe').is_file():
            raise RuntimeError('Build the native single-file executable first.')
        shutil.copyfile(ROOT / 'docs/使用说明.md', OUT / '使用说明.md')
        license_files = [(p, 'licenses/' + p.name) for p in (ROOT / 'assets/licenses').glob('*') if p.is_file()]
        make_archive(OUT / '归档-Windows单文件版.zip', [(OUT / '归档.exe', '归档.exe'), (OUT / '使用说明.md', '使用说明.md'), (ROOT / 'THIRD_PARTY_NOTICES.md', 'THIRD_PARTY_NOTICES.md'), (ROOT / 'LICENSE', 'LICENSE')] + license_files)
    make_archive(OUT / '归档-Python源码.zip', source_files())
    print('Release archives ready in', OUT)


if __name__ == '__main__':
    main()
