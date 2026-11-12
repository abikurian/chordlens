"""Generate a PyInstaller Windows VSVersionInfo file from VERSION and backend/version.py."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.version import (  # noqa: E402
    APP_DESCRIPTION,
    APP_NAME,
    COMPANY_NAME,
    COPYRIGHT,
    get_version,
    get_version_tuple,
)


def generate_version_info(out_path: Path) -> Path:
    ver_str = get_version()
    v = get_version_tuple()
    ver_4 = f"{v[0]}.{v[1]}.{v[2]}.{v[3]}"
    content = f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={v},
    prodvers={v},
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
          u'040904B0',
          [
            StringStruct(u'CompanyName', u'{COMPANY_NAME}'),
            StringStruct(u'FileDescription', u'{APP_DESCRIPTION}'),
            StringStruct(u'FileVersion', u'{ver_4}'),
            StringStruct(u'InternalName', u'{APP_NAME}'),
            StringStruct(u'LegalCopyright', u'{COPYRIGHT}'),
            StringStruct(u'OriginalFilename', u'{APP_NAME}.exe'),
            StringStruct(u'ProductName', u'{APP_NAME}'),
            StringStruct(u'ProductVersion', u'{ver_str}'),
          ]
        )
      ]
    ),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    return out_path


if __name__ == "__main__":
    target = ROOT / "build" / "version_info.txt"
    generate_version_info(target)
    print(f"Wrote {target}")
