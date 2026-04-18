# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for QAcousticCamera.
# Build with: pyinstaller QAcousticCamera.spec
#
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

datas = []
datas += collect_data_files('QInstrument',  includes=['**/*.ui', '**/*.png'])
datas += collect_data_files('QPolargraph',  includes=['**/*.ui', '**/*.png'])
datas += collect_data_files('pyqtgraph')
datas += [('docs/icon.png', 'docs'), ('docs/demo.csv', 'docs')]

hiddenimports = (
    collect_submodules('QInstrument') +
    collect_submodules('QPolargraph') +
    collect_submodules('pyqtgraph') +
    [
        'scipy.interpolate',
        'scipy.spatial',
        'scipy.spatial.transform',
        'scipy._lib.messagestream',
        'pandas',
        'pandas._libs.tslibs.np_datetime',
        'pandas._libs.tslibs.nattype',
        'pandas._libs.tslibs.timedeltas',
    ]
)

if sys.platform == 'win32':
    icon = 'docs/icon.ico'
elif sys.platform == 'darwin':
    icon = 'docs/icon.icns'
else:
    icon = 'docs/icon.png'

a = Analysis(
    ['QAcousticCamera.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib'],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='QAcousticCamera',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name='QAcousticCamera',
)

if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='QAcousticCamera.app',
        icon='docs/icon.icns',
        bundle_identifier='edu.nyu.physics.QAcousticCamera',
        info_plist={
            'CFBundleShortVersionString': '1.1.0',
            'NSHighResolutionCapable': True,
        },
    )
