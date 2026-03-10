# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for simcoach desktop application.

Build:
    pyinstaller simcoach_app.spec

Output:
    dist/simcoach/simcoach.exe   (single-folder distribution)
"""

from pathlib import Path

block_cipher = None
src_root = Path("src/simcoach")

# Data files to bundle alongside the executable
datas = [
    (str(src_root / "report" / "templates"), "simcoach/report/templates"),
    (str(src_root / "app" / "style" / "icons"), "simcoach/app/style/icons"),
    ("configs/config.example.yaml", "configs"),
]

# Include .env.example if it exists
if Path(".env.example").exists():
    datas.append((".env.example", "."))

a = Analysis(
    [str(src_root / "app" / "__main__.py")],
    pathex=["src"],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "simcoach.telemetry_bridge.ac_shared_memory",
        "simcoach.telemetry_bridge.mock_source",
        "simcoach.cli.main",
        "PySide6.QtWidgets",
        "PySide6.QtCore",
        "PySide6.QtGui",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="simcoach",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No console window — GUI only
    icon=str(src_root / "app" / "style" / "icons" / "app.ico")
    if (src_root / "app" / "style" / "icons" / "app.ico").exists()
    else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name="simcoach",
)
