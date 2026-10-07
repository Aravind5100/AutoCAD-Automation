# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the Room Layer Tool (PySide6 window).

Build:   .venv\\Scripts\\python.exe -m PyInstaller build_exe.spec --noconfirm
Output:  dist\\Room Layer Tool\\Room Layer Tool.exe   (one folder, no Python needed)
Check:   "dist\\Room Layer Tool\\Room Layer Tool.exe" --selftest report.txt
"""

from PyInstaller.utils.hooks import collect_data_files

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    # ezdxf ships font metrics used to measure text (room label extents)
    datas=collect_data_files('ezdxf'),
    hiddenimports=[
        # Project modules (several are imported lazily inside functions)
        'qt_ui',
        'pipeline',
        'selftest',
        'autocad_scanner',
        'annotation_writer',
        'dwg_converter',
        'polygon_matcher',
        'metadata_utils',
        'spreadsheet_loader',
        'config',
        'utils',
        # Dependencies
        'pandas',
        'openpyxl',
        'xlrd',
        'ezdxf',
        'pythoncom',
        'pywintypes',
        'win32com',
        'win32com.client',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'ui',            # the old Tkinter window is not shipped
        'matplotlib', 'scipy', 'numpy.tests', 'pytest', 'IPython', 'jupyter',
        'tests',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Room Layer Tool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                      # UPX can corrupt Qt DLLs
    console=False,                  # GUI only
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Room Layer Tool',
)
