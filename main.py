import sys
import io
import os
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
os.environ['QT_LOGGING_RULES'] = '*.debug=false;qt.qpa.*=false'  # Qt DPI警告を抑制

# PyInstaller exe環境でTcl/Tkデータパスを明示設定（init.tcl検索エラー対策）
# rthook_tcltk.py ランタイムフックが先に実行済み。ここでは再チェック+診断ログ出力。
if getattr(sys, 'frozen', False):
    _meipass = sys._MEIPASS
    _diag_lines = [f"_MEIPASS: {_meipass}"]

    if 'TCL_LIBRARY' in os.environ:
        _tcl_env = os.environ['TCL_LIBRARY']
        _has_init = os.path.isfile(os.path.join(_tcl_env, 'init.tcl'))
        _diag_lines.append(f"TCL_LIBRARY={_tcl_env} (init.tcl exists: {_has_init})")
        if not _has_init:
            # ランタイムフックが見つけられなかった場合、再探索
            _tcl_found = False
            for _candidate in [
                os.path.join(_meipass, '_tcl_data'),
                os.path.join(_meipass, 'tcl'),
                os.path.join(_meipass, 'tcl8.6'),
                os.path.join(_meipass, 'tcl', 'tcl8.6'),
                os.path.join(_meipass, 'lib', 'tcl8.6'),
            ]:
                if os.path.isfile(os.path.join(_candidate, 'init.tcl')):
                    os.environ['TCL_LIBRARY'] = _candidate
                    _diag_lines.append(f"Found init.tcl at: {_candidate}")
                    _tcl_found = True
                    break
            if not _tcl_found:
                for _root, _dirs, _files in os.walk(_meipass):
                    if 'init.tcl' in _files:
                        os.environ['TCL_LIBRARY'] = _root
                        _diag_lines.append(f"Found init.tcl (recursive) at: {_root}")
                        _tcl_found = True
                        break
                if not _tcl_found:
                    _diag_lines.append("ERROR: init.tcl NOT FOUND ANYWHERE in _MEIPASS")
    else:
        _diag_lines.append("TCL_LIBRARY not set by runtime hook!")
        for _candidate in [
            os.path.join(_meipass, '_tcl_data'),
            os.path.join(_meipass, 'tcl'),
            os.path.join(_meipass, 'tcl8.6'),
            os.path.join(_meipass, 'tcl', 'tcl8.6'),
            os.path.join(_meipass, 'lib', 'tcl8.6'),
        ]:
            if os.path.isfile(os.path.join(_candidate, 'init.tcl')):
                os.environ['TCL_LIBRARY'] = _candidate
                _diag_lines.append(f"Found init.tcl at: {_candidate}")
                break
        else:
            for _root, _dirs, _files in os.walk(_meipass):
                if 'init.tcl' in _files:
                    os.environ['TCL_LIBRARY'] = _root
                    _diag_lines.append(f"Found init.tcl (recursive) at: {_root}")
                    break

    # TK_LIBRARYも同様にチェック（簡略版）
    if 'TK_LIBRARY' not in os.environ or not os.path.isfile(
        os.path.join(os.environ.get('TK_LIBRARY', ''), 'tk.tcl')
    ):
        for _candidate in [
            os.path.join(_meipass, '_tk_data'),
            os.path.join(_meipass, 'tk'),
            os.path.join(_meipass, 'tk8.6'),
            os.path.join(_meipass, 'tcl', 'tk8.6'),
            os.path.join(_meipass, 'lib', 'tk8.6'),
        ]:
            if os.path.isfile(os.path.join(_candidate, 'tk.tcl')):
                os.environ['TK_LIBRARY'] = _candidate
                break
        else:
            for _root, _dirs, _files in os.walk(_meipass):
                if 'tk.tcl' in _files:
                    os.environ['TK_LIBRARY'] = _root
                    break

    # 診断ログをファイルに書き出し（次回のデバッグ用）
    try:
        _diag_path = os.path.join(os.path.dirname(sys.executable), 'tcl_diag.log')
        with open(_diag_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(_diag_lines))
    except Exception:
        pass

import tkinter as tk
from dotenv import load_dotenv

# PyInstallerでの相対パス解決用にsrcをパスへ追加
BASE_DIR = getattr(sys, "_MEIPASS", os.path.abspath(os.path.dirname(__file__)))
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

# ロガーを最初にインポート（他のモジュールより先に初期化）
from src.logger import logger  # noqa: E402

import customtkinter as ctk  # noqa: E402
import src.overlay_server  # noqa: E402
import src.voice_listener  # noqa: E402
import src.translator      # noqa: E402
from src.gui import KototsunaApp  # noqa: E402

# .envの読み込み
load_dotenv()

# Windows環境での文字化け対策
# 注意: --windowed (GUIモード) で起動した場合、sys.stdout は None になるためチェックが必要
if sys.platform == "win32":
    if sys.stdout is not None:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    if sys.stderr is not None:
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

def create_splash_screen():
    """起動時のスプラッシュスクリーンを作成"""
    splash = tk.Toplevel()
    splash.title("ことつな！")
    splash.overrideredirect(True)  # ウィンドウ枠を非表示

    # 画面中央に配置
    window_width = 400
    window_height = 400
    screen_width = splash.winfo_screenwidth()
    screen_height = splash.winfo_screenheight()
    x = (screen_width - window_width) // 2
    y = (screen_height - window_height) // 2
    splash.geometry(f"{window_width}x{window_height}+{x}+{y}")

    # 背景色
    splash.configure(bg="#0C1424")

    # アイコン画像を表示
    try:
        from PIL import Image, ImageTk
        icon_path = os.path.join(BASE_DIR, "assets", "icon.png")
        if os.path.exists(icon_path):
            # PILで画像を開いてリサイズ
            pil_image = Image.open(icon_path)
            # 元の画像のアスペクト比を保持して250x250にリサイズ
            pil_image.thumbnail((250, 250), Image.Resampling.LANCZOS)
            icon_image = ImageTk.PhotoImage(pil_image)

            icon_label = tk.Label(splash, image=icon_image, bg="#0C1424")
            icon_label.image = icon_image  # type: ignore[attr-defined]  # 参照を保持
            icon_label.pack(pady=40)
    except Exception as e:
        logger.warning(f"スプラッシュスクリーンのアイコン読み込みエラー: {e}")

    # ローディングテキスト
    loading_label = tk.Label(
        splash,
        text="読み込み中...",
        font=("Segoe UI", 16),
        fg="#9BAEC6",
        bg="#0C1424"
    )
    loading_label.pack(pady=20)

    # アプリ名
    app_name_label = tk.Label(
        splash,
        text="ことつな！",
        font=("Segoe UI", 24, "bold"),
        fg="#22C55E",
        bg="#0C1424"
    )
    app_name_label.pack(pady=10)

    splash.update()
    return splash

def on_closing():
    """ウィンドウを閉じる際のクリーンアップ処理"""
    try:
        # アプリケーションのリソースを解放
        app.cleanup_resources()
    except Exception as e:
        logger.error(f"クリーンアップ中のエラー: {e}", exc_info=True)
    finally:
        # ウィンドウを破棄
        root.destroy()

if __name__ == '__main__':
    # 前回アップデート後のクリーンアップ
    if "--cleanup" in sys.argv:
        import time
        time.sleep(2)
        from src.updater import cleanup_old_exe
        cleanup_old_exe()

    # メインウィンドウを作成（非表示）
    root = ctk.CTk()
    root.withdraw()  # 最初は非表示

    # スプラッシュスクリーンを表示
    splash = create_splash_screen()

    # メインアプリを初期化
    def init_app():
        global app
        try:
            app = KototsunaApp(root)
            # ウィンドウを閉じる際のプロトコルを設定
            root.protocol("WM_DELETE_WINDOW", on_closing)
            # スプラッシュスクリーンを閉じる
            splash.destroy()
            # メインウィンドウを表示
            root.deiconify()
        except Exception as e:
            logger.critical(f"アプリケーション初期化エラー: {e}", exc_info=True)
            splash.destroy()
            root.destroy()

    # 少し遅延してメインアプリを初期化（スプラッシュが表示されるように）
    root.after(500, init_app)
    root.mainloop()
