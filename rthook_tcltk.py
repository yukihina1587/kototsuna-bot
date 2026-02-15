# PyInstaller runtime hook: Tcl/Tk ZIPを展開 + 診断出力
import os
import sys
import zipfile
import tempfile

_meipass = getattr(sys, '_MEIPASS', None)

# 詳細診断をファイルに出力
_diag_path = os.path.join(tempfile.gettempdir(), 'kototsuna_rthook_diag.txt')
try:
    with open(_diag_path, 'w', encoding='utf-8') as _df:
        _df.write(f"meipass={_meipass}\n")
        _df.write(f"frozen={getattr(sys, 'frozen', False)}\n")

        if _meipass:
            _zip_path = os.path.join(_meipass, 'tcl_tk_data.zip')
            _tcl_dir = os.path.join(_meipass, '_tcl_data')
            _tk_dir = os.path.join(_meipass, '_tk_data')

            _df.write(f"zip_exists={os.path.isfile(_zip_path)}\n")
            if os.path.isfile(_zip_path):
                _df.write(f"zip_size={os.path.getsize(_zip_path)}\n")

            # _MEIPASS直下のディレクトリのみ一覧
            _df.write("meipass_dirs=\n")
            try:
                for entry in sorted(os.listdir(_meipass)):
                    full = os.path.join(_meipass, entry)
                    if os.path.isdir(full):
                        _df.write(f"  {entry}/\n")
            except Exception as e:
                _df.write(f"  ERROR: {e}\n")

            # customtkinter パス確認
            _ctk_dir = os.path.join(_meipass, 'customtkinter')
            _ctk_assets = os.path.join(_ctk_dir, 'assets')
            _ctk_themes = os.path.join(_ctk_assets, 'themes')
            _ctk_blue = os.path.join(_ctk_themes, 'blue.json')
            _df.write(f"ctk_dir_exists={os.path.isdir(_ctk_dir)}\n")
            _df.write(f"ctk_assets_exists={os.path.isdir(_ctk_assets)}\n")
            _df.write(f"ctk_themes_exists={os.path.isdir(_ctk_themes)}\n")
            _df.write(f"ctk_blue_json_exists={os.path.isfile(_ctk_blue)}\n")
            if os.path.isdir(_ctk_dir):
                _df.write("ctk_dir_contents=\n")
                try:
                    for entry in sorted(os.listdir(_ctk_dir)):
                        _df.write(f"  {entry}\n")
                except Exception as e:
                    _df.write(f"  ERROR: {e}\n")

            # _tcl_data確認
            _df.write(f"tcl_dir_exists={os.path.isdir(_tcl_dir)}\n")
            _df.write(f"init_tcl_exists={os.path.isfile(os.path.join(_tcl_dir, 'init.tcl'))}\n")

            # ZIP展開を試行
            if os.path.isfile(_zip_path):
                _df.write("zip_extraction=attempting\n")
                try:
                    with zipfile.ZipFile(_zip_path, 'r') as zf:
                        _df.write(f"zip_namelist_count={len(zf.namelist())}\n")
                        zf.extractall(_meipass)
                    _df.write("zip_extraction=success\n")
                except Exception as e:
                    _df.write(f"zip_extraction=FAILED: {e}\n")
                _df.write(f"init_tcl_after_extract={os.path.isfile(os.path.join(_tcl_dir, 'init.tcl'))}\n")
            else:
                _df.write("zip_extraction=skipped\n")

            # TCL_LIBRARY/TK_LIBRARYを設定
            if os.path.isdir(_tcl_dir):
                os.environ['TCL_LIBRARY'] = _tcl_dir
                _df.write(f"set_TCL_LIBRARY={_tcl_dir}\n")
            if os.path.isdir(_tk_dir):
                os.environ['TK_LIBRARY'] = _tk_dir
                _df.write(f"set_TK_LIBRARY={_tk_dir}\n")

            # _MEIPASS内の総ファイル数
            _total = sum(len(f) for _, _, f in os.walk(_meipass))
            _df.write(f"total_files_in_meipass={_total}\n")
        else:
            _df.write("NOT FROZEN - skipping\n")
except Exception:
    pass

# ZIP展開（フォールバック）
if _meipass:
    _zip_path = os.path.join(_meipass, 'tcl_tk_data.zip')
    _tcl_dir = os.path.join(_meipass, '_tcl_data')
    _tk_dir = os.path.join(_meipass, '_tk_data')
    if os.path.isfile(_zip_path) and not os.path.isfile(os.path.join(_tcl_dir, 'init.tcl')):
        try:
            with zipfile.ZipFile(_zip_path, 'r') as zf:
                zf.extractall(_meipass)
        except Exception:
            pass
    if os.path.isdir(_tcl_dir):
        os.environ['TCL_LIBRARY'] = _tcl_dir
    if os.path.isdir(_tk_dir):
        os.environ['TK_LIBRARY'] = _tk_dir
