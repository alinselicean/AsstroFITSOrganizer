import shutil
import subprocess
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
VERSION_FILE = APP_DIR / "version.txt"
TEMP_VERSION_INFO = APP_DIR / "version_info.txt"

APP_NAME = "AstroFITSOrganizer"
SCRIPT_NAME = "astro_organizer.py"
AUTHOR = "alinselicean"
DESCRIPTION = "Astro FITS Organizer & Deduplicator"
PRODUCT_NAME = "Astro FITS Organizer"


def bump_version(bump_type: str = "patch") -> tuple[int, int, int, int]:
    """Reads version.txt (default 1.0.0), increments it, and saves the new version."""
    if VERSION_FILE.exists():
        raw = VERSION_FILE.read_text(encoding="utf-8").strip()
        parts = [int(x) for x in raw.split(".")]
        while len(parts) < 3:
            parts.append(0)
        major, minor, patch = parts[:3]
    else:
        major, minor, patch = 1, 0, 0

    if bump_type == "major":
        major += 1
        minor = 0
        patch = 0
    elif bump_type == "minor":
        minor += 1
        patch = 0
    else:
        patch += 1

    VERSION_FILE.write_text(f"{major}.{minor}.{patch}\n", encoding="utf-8")
    return (major, minor, patch, 0)


def write_pyinstaller_version_file(ver_tuple: tuple[int, int, int, int]):
    """Generates the VSVersionInfo file required by PyInstaller on Windows."""
    ver_str = ".".join(str(x) for x in ver_tuple)
    content = f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={ver_tuple},
    prodvers={ver_tuple},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          '040904B0',
          [
            StringStruct('CompanyName', '{AUTHOR}'),
            StringStruct('FileDescription', '{DESCRIPTION}'),
            StringStruct('FileVersion', '{ver_str}'),
            StringStruct('InternalName', '{APP_NAME}'),
            StringStruct('LegalCopyright', '© 2026 {AUTHOR}'),
            StringStruct('OriginalFilename', '{APP_NAME}.exe'),
            StringStruct('ProductName', '{PRODUCT_NAME}'),
            StringStruct('ProductVersion', '{ver_str}')
          ]
        )
      ]
    ),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    TEMP_VERSION_INFO.write_text(content, encoding="utf-8")


def main():
    bump_type = sys.argv[1].lower() if len(sys.argv) > 1 else "patch"
    ver_tuple = bump_version(bump_type)
    ver_short = f"{ver_tuple[0]}.{ver_tuple[1]}.{ver_tuple[2]}"

    print(f"Building {APP_NAME} v{ver_short}...")
    write_pyinstaller_version_file(ver_tuple)

    # Clean previous build artifacts safely
    for folder in ("build", "dist"):
        target = APP_DIR / folder
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--windowed",
        "--clean",
        "--name",
        APP_NAME,
        "--version-file",
        str(TEMP_VERSION_INFO),
        str(APP_DIR / SCRIPT_NAME),
    ]

    try:
        subprocess.run(cmd, cwd=str(APP_DIR), check=True)
        print(f"\nSucces! Executabil generat: dist\\{APP_NAME}.exe (v{ver_short})")
    finally:
        if TEMP_VERSION_INFO.exists():
            TEMP_VERSION_INFO.unlink()


if __name__ == "__main__":
    main()