# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = []
binaries = []
hiddenimports = []
tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

# customtkinterテーマファイルを明示的に追加（CI環境でhookが欠落する場合の保険）
import customtkinter
ctk_path = os.path.dirname(customtkinter.__file__)
ctk_assets = os.path.join(ctk_path, 'assets')
if os.path.isdir(ctk_assets):
    for root, dirs, files in os.walk(ctk_assets):
        for f in files:
            src = os.path.join(root, f)
            dst = os.path.join('customtkinter', 'assets', os.path.relpath(root, ctk_assets))
            datas.append((src, dst))

# Tcl/Tkライブラリを収集（ディレクトリ単位・標準PyInstallerフォーマット）
import tkinter
_tcl = tkinter.Tcl()
_tcl_lib = _tcl.eval('info library')  # e.g. C:/Python312/tcl/tcl8.6
_tcl_ver = _tcl.eval('info patchlevel').rsplit('.', 1)[0]  # e.g. "8.6"
_tk_lib = os.path.join(os.path.dirname(_tcl_lib), f'tk{_tcl_ver}')
print(f"[SPEC] Tcl library: {_tcl_lib} (exists={os.path.isdir(_tcl_lib)})")
print(f"[SPEC] Tk  library: {_tk_lib} (exists={os.path.isdir(_tk_lib)})")

# ディレクトリ丸ごとdatasに追加（PyInstallerが中身をフラットに展開する）
if os.path.isdir(_tcl_lib):
    datas += [(_tcl_lib, '_tcl_data')]
    print(f"[SPEC] Added _tcl_data from {_tcl_lib}")
if os.path.isdir(_tk_lib):
    datas += [(_tk_lib, '_tk_data')]
    print(f"[SPEC] Added _tk_data from {_tk_lib}")

# pyaudioのC拡張を収集
tmp_ret = collect_all('pyaudio')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

# tkinterwebを収集（これが無いとEXE化した際に読み込めない）
tmp_ret = collect_all('tkinterweb')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

# PyQt6とWebEngineを収集（完全なブラウザエンジンのHTML表示用）
for module in ['PyQt6', 'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets', 'PyQt6.QtWebEngineWidgets', 'PyQt6.QtWebEngineCore']:
    try:
        tmp_ret = collect_all(module)
        datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
    except Exception as e:
        print(f"Warning: Could not collect {module}: {e}")

# srcパッケージ内の全サブモジュールを収集
hiddenimports += collect_submodules('src')

# アイコンファイルを含める（PNGとICOの両方）
datas += [('assets/icon.png', 'assets'), ('assets/icon_fullsize.ico', 'assets')]
datas += [('src', 'src')] # srcフォルダごとデータとしてコピーもしておく（念のため）
datas += [('overlay.html', '.')]  # オーバーレイHTML


a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['rthook_tcltk.py'],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Kototsuna',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # GUIモード（コンソールウィンドウを非表示）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon_fullsize.ico',  # パディング付き256x256高解像度ICOファイル
)
