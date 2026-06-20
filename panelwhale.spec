# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for PanelWhale on Windows.

Build:  .venv\Scripts\python -m PyInstaller panelwhale.spec
Output: dist\PanelWhale.exe
"""

import sys
import os
from pathlib import Path

_root = Path(SPECPATH)  # directory containing this .spec file

a = Analysis(
    [str(_root / "main.py")],
    pathex=[str(_root)],
    binaries=[],
    datas=[
        (str(_root / "monitor" / "panel_template.html"), "monitor"),
        (str(_root / "monitor" / "deepseek-color.png"), "monitor"),
    ],
    hiddenimports=[
        "pystray",
        "pystray._win32",
        "PIL",
        "PIL.Image",
        "PIL.ImageDraw",
        "PIL.ImageFont",
        "win32api",
        "win32gui",
        "win32con",
        "win32ui",
        "monitor",
        "monitor.config",
        "monitor.api",
        "monitor.store",
        "monitor.panel",
        "monitor.report",
        "monitor.indicator",
        "monitor.windows_tray",
        "monitor.settings",
        "monitor.usage_api",
        "monitor.usage_cache",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "gi",
        "cairo",
        "Gtk",
        "Gdk",
        "GObject",
        "GLib",
        "pango",
        "atk",
        "AppIndicator3",
        "AyatanaAppIndicator3",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# Icon for the .exe — use the DeepSeek logo if available
icon_path = str(_root / "monitor" / "deepseek-color.png")
_exe_icon = icon_path if os.path.isfile(icon_path) else None

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="PanelWhale",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,           # no terminal window on Windows
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_exe_icon,
)
