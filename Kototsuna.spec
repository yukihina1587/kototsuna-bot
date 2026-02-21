# -*- mode: python ; coding: utf-8 -*-
import os
import zipfile
import tempfile as _tmpmod
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

# Tcl/TkデータをZIPにまとめてバンドル
# PyInstallerのdatasパイプラインで個別ファイルが消失する問題のワークアラウンド:
# 832+175の個別ファイルではなく1つのZIPとしてバンドルし、
# カスタムランタイムフック(rthook_tcltk.py)で起動時に展開する。
import tkinter as _tk_mod
_tcl_interp = _tk_mod.Tcl()
_tcl_lib = _tcl_interp.eval('info library')
_tcl_ver = _tcl_interp.eval('info patchlevel').rsplit('.', 1)[0]
_tk_lib = os.path.join(os.path.dirname(_tcl_lib), f'tk{_tcl_ver}')

_tcl_zip_path = os.path.join(_tmpmod.gettempdir(), 'tcl_tk_data.zip')
_zip_count = 0
_init_found = False
with zipfile.ZipFile(_tcl_zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
    if os.path.isdir(_tcl_lib):
        for _root, _dirs, _files in os.walk(_tcl_lib):
            for _f in _files:
                _src = os.path.join(_root, _f)
                _rel = os.path.relpath(_root, _tcl_lib)
                _arcname = _f if _rel == '.' else os.path.join(_rel, _f)
                zf.write(_src, os.path.join('_tcl_data', _arcname))
                _zip_count += 1
                if _f == 'init.tcl' and _rel == '.':
                    _init_found = True
    if os.path.isdir(_tk_lib):
        for _root, _dirs, _files in os.walk(_tk_lib):
            for _f in _files:
                _src = os.path.join(_root, _f)
                _rel = os.path.relpath(_root, _tk_lib)
                _arcname = _f if _rel == '.' else os.path.join(_rel, _f)
                zf.write(_src, os.path.join('_tk_data', _arcname))
                _zip_count += 1

_zip_size = os.path.getsize(_tcl_zip_path)
print(f"[SPEC] Tcl/Tk ZIP: {_zip_count} files, {_zip_size:,} bytes (init.tcl: {'FOUND' if _init_found else 'MISSING'})")
datas.append((_tcl_zip_path, '.'))

# pyaudioのC拡張を収集
tmp_ret = collect_all('pyaudio')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
print(f"[SPEC] pyaudio collect_all: datas={len(tmp_ret[0])}, binaries={len(tmp_ret[1])}, hiddenimports={tmp_ret[2]}")
for _b in tmp_ret[1]:
    print(f"[SPEC]   binary: {_b}")
# _portaudioはCエクステンション(.pyd)のためcollect_allで漏れる場合がある
hiddenimports += ['pyaudio._portaudio']
# .pydファイルを明示的にバイナリとして追加（collect_all/hiddenimportsで漏れる場合の保険）
import pyaudio as _pa_mod
_pa_dir = os.path.dirname(_pa_mod.__file__)
_portaudio_found = False
for _f in os.listdir(_pa_dir):
    if _f.startswith('_portaudio') and (_f.endswith('.pyd') or _f.endswith('.so')):
        binaries.append((os.path.join(_pa_dir, _f), 'pyaudio'))
        print(f"[SPEC] Explicitly added pyaudio binary: {_f}")
        _portaudio_found = True
        break
if not _portaudio_found:
    print(f"[SPEC] WARNING: _portaudio.pyd not found in {_pa_dir}")
    print(f"[SPEC]   contents: {os.listdir(_pa_dir)}")

# tkinterwebを収集（これが無いとEXE化した際に読み込めない）
tmp_ret = collect_all('tkinterweb')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

# PyQt6: 必要なモジュールのみ明示指定（全モジュール収集による警告・肥大化を防止）
hiddenimports += [
    'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets',
    'PyQt6.QtWebEngineWidgets', 'PyQt6.QtWebEngineCore',
    'PyQt6.QtNetwork', 'PyQt6.QtWebChannel', 'PyQt6.QtPrintSupport',
]
# PyQt6のデータファイルとバイナリはパッケージから収集（WebEngineリソース等）
try:
    tmp_ret = collect_all('PyQt6')
    datas += tmp_ret[0]; binaries += tmp_ret[1]
    # hiddenimportsはcollect_allから取らない（不要な全モジュールが入るため）
except Exception as e:
    print(f"Warning: Could not collect PyQt6: {e}")

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
    hookspath=['hooks'],  # 標準hook-_tkinter.pyをオーバーライド（Tcl/Tkデータ干渉防止）
    hooksconfig={},
    runtime_hooks=['rthook_tcltk.py'],  # ZIP展開フック（標準rthookより先に実行）
    excludes=[
        # 未使用PyQt6モジュールを除外（ビルド警告削減・exe軽量化）
        'PyQt6.QtBluetooth', 'PyQt6.QAxContainer', 'PyQt6.QtDBus',
        'PyQt6.QtDesigner', 'PyQt6.QtHelp', 'PyQt6.QtMultimedia',
        'PyQt6.QtMultimediaWidgets', 'PyQt6.QtNfc', 'PyQt6.QtOpenGL',
        'PyQt6.QtOpenGLWidgets', 'PyQt6.QtPdf', 'PyQt6.QtPdfWidgets',
        'PyQt6.QtPositioning', 'PyQt6.QtQml', 'PyQt6.QtQuick',
        'PyQt6.QtQuick3D', 'PyQt6.QtQuickWidgets', 'PyQt6.QtRemoteObjects',
        'PyQt6.QtSensors', 'PyQt6.QtSerialPort', 'PyQt6.QtSpatialAudio',
        'PyQt6.QtSql', 'PyQt6.QtStateMachine', 'PyQt6.QtSvg',
        'PyQt6.QtSvgWidgets', 'PyQt6.QtTest', 'PyQt6.QtTextToSpeech',
        'PyQt6.QtWebEngineQuick', 'PyQt6.QtWebSockets', 'PyQt6.QtXml',
        'PyQt6.lupdate',
    ],
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
    runtime_tmpdir='.',  # exe隣に展開（%TEMP%のWindows Defenderスキャン回避）
    console=False,  # GUIモード（コンソールウィンドウを非表示）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon_fullsize.ico',  # パディング付き256x256高解像度ICOファイル
)
