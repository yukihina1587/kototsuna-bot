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
ctk_alt_assets = os.path.join(ctk_path, 'windows', 'widgets', 'theme', 'assets')
if os.path.isdir(ctk_assets):
    for root, dirs, files in os.walk(ctk_assets):
        for f in files:
            src = os.path.join(root, f)
            dst = os.path.join('customtkinter', 'assets', os.path.relpath(root, ctk_assets))
            datas.append((src, dst))
# CustomTkinterのassetsディレクトリを丸ごと追加（blue.json欠落の再発防止）
if os.path.isfile(os.path.join(ctk_assets, 'themes', 'blue.json')):
    datas.append((ctk_assets, os.path.join('customtkinter', 'assets')))
    print(f"[SPEC] CustomTkinter assets: {ctk_assets} -> customtkinter/assets")
elif os.path.isfile(os.path.join(ctk_alt_assets, 'themes', 'blue.json')):
    datas.append((ctk_alt_assets, os.path.join('customtkinter', 'assets')))
    print(f"[SPEC] CustomTkinter assets(alt): {ctk_alt_assets} -> customtkinter/assets")
else:
    print("[SPEC][WARN] CustomTkinter blue.json not found in expected asset paths")

# Tcl/Tkデータを明示収集（PyInstaller標準フックが期待する _tcl_data/_tk_data に配置）
# 標準hook-_tkinter.pyの収集がCI環境で失敗するケースへの保険
import tkinter
_tcl = tkinter.Tcl()
_tcl_lib = _tcl.eval('info library')
_tcl_ver = _tcl.eval('info patchlevel').rsplit('.', 1)[0]
_tk_lib = os.path.join(os.path.dirname(_tcl_lib), f'tk{_tcl_ver}')
if os.path.isdir(_tcl_lib):
    # Keep both legacy and _internal layouts for onefile extraction differences.
    datas += [(_tcl_lib, '_tcl_data'), (_tcl_lib, os.path.join('_internal', '_tcl_data'))]
    print(f"[SPEC] Tcl: {_tcl_lib} -> _tcl_data, _internal/_tcl_data")
if os.path.isdir(_tk_lib):
    datas += [(_tk_lib, '_tk_data'), (_tk_lib, os.path.join('_internal', '_tk_data'))]
    print(f"[SPEC] Tk:  {_tk_lib} -> _tk_data, _internal/_tk_data")

# pyaudioのC拡張を収集
tmp_ret = collect_all('pyaudio')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

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
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['hooks/rthook_tk_paths.py'],
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
    runtime_tmpdir=None,
    console=False,  # GUIモード（コンソールウィンドウを非表示）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon_fullsize.ico',  # パディング付き256x256高解像度ICOファイル
)
