# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

hidden_imports = (
    collect_submodules('webview') +
    collect_submodules('pydantic_settings') +
    collect_submodules('bcrypt') +
    collect_submodules('uvicorn') +
    collect_submodules('fastapi') +
    collect_submodules('starlette') +
    collect_submodules('jinja2') +
    collect_submodules('motor') +
    collect_submodules('pymongo') +
    collect_submodules('dns') +
    collect_submodules('pandas') +
    collect_submodules('numpy') +
    collect_submodules('openpyxl')
)

datas = [('templates', 'templates'), ('static', 'static')]
datas += collect_data_files('pandas')
datas += collect_data_files('openpyxl')
datas += collect_data_files('motor')
datas += collect_data_files('pymongo')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='BloomOperator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='BloomOperator',
)
