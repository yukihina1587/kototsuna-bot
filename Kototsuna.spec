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

# sherpa-onnxのネイティブDLLと依存ファイルを収集
tmp_ret = collect_all('sherpa_onnx')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
print(f"[SPEC] sherpa_onnx collect_all: datas={len(tmp_ret[0])}, binaries={len(tmp_ret[1])}, hiddenimports={len(tmp_ret[2])}")

# sounddeviceとPortAudioのネイティブライブラリを収集
tmp_ret = collect_all('sounddevice')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
print(f"[SPEC] sounddevice collect_all: datas={len(tmp_ret[0])}, binaries={len(tmp_ret[1])}, hiddenimports={len(tmp_ret[2])}")
# _sounddevice_dataにPortAudioのDLLが含まれる場合がある
try:
    tmp_ret = collect_all('_sounddevice_data')
    datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
    print(f"[SPEC] _sounddevice_data collect_all: datas={len(tmp_ret[0])}, binaries={len(tmp_ret[1])}")
except Exception:
    print("[SPEC] _sounddevice_data not found (may not be needed)")

# CTranslate2 + SentencePiece（ローカル翻訳エンジン）のネイティブDLLと依存ファイルを収集
tmp_ret = collect_all('ctranslate2')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
print(f"[SPEC] ctranslate2 collect_all: datas={len(tmp_ret[0])}, binaries={len(tmp_ret[1])}, hiddenimports={len(tmp_ret[2])}")

tmp_ret = collect_all('sentencepiece')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
print(f"[SPEC] sentencepiece collect_all: datas={len(tmp_ret[0])}, binaries={len(tmp_ret[1])}, hiddenimports={len(tmp_ret[2])}")

# STTモデルファイルを同梱（models/ディレクトリ）
_models_dir = os.path.join('.', 'models')
if os.path.isdir(_models_dir):
    datas.append((_models_dir, 'models'))
    print(f"[SPEC] Added models/ directory to datas")
else:
    print(f"[SPEC] WARNING: models/ directory not found. STT models must be present at build time.")

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
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    name='Kototsuna',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    console=True,  # bootloaderエラーをstderrへ出力（MessageBox回避）
    hide_console='hide-early',  # bootloader起動直後にコンソールを非表示
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon_fullsize.ico',  # パディング付き256x256高解像度ICOファイル
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Kototsuna',
)
