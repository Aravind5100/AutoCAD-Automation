# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for AutoCAD Room Annotation Tool.
Builds a single-folder distributable with all dependencies bundled.
"""

import sys
import os

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        # Project modules (some are imported dynamically in ui.py)
        'autocad_scanner',
        'annotation_writer',
        'dwg_converter',
        'polygon_matcher',
        'metadata_utils',
        'spreadsheet_loader',
        'file_loader',
        'matcher',
        'config',
        'utils',
        'ui',
        # Dependencies
        'pandas',
        'openpyxl',
        'xlrd',
        'ezdxf',
        'pythoncom',
        'win32com',
        'win32com.client',
        'pywintypes',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'scipy',
        'numpy.tests',
        'pytest',
        'IPython',
        'jupyter',
    ],
    noarchive=False,
    optimize=0,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AutoCAD Room Annotator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No console window — GUI only
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AutoCAD Room Annotator',
)
