"""Repair text launchers after a local project rename, keeping installed packages."""
from pathlib import Path
import sys


def relocate(old_root, new_root):
    old_root, new_root = str(Path(old_root)), Path(new_root)
    venv = new_root / '.venv'
    for path in [*(venv / 'bin').glob('*'), venv / 'pyvenv.cfg']:
        if path.is_symlink() or not path.is_file():
            continue
        try:
            content = path.read_text()
        except UnicodeError:
            continue
        updated = content.replace(old_root + '/', str(new_root) + '/')
        if updated != content:
            path.write_text(updated)


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('Usage: relocate_venv.py OLD_PROJECT_ROOT NEW_PROJECT_ROOT')
    relocate(*sys.argv[1:])
