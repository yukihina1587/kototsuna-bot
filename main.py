import sys
import io
import os
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

# --- 多重起動防止 (Windows Named Mutex) ---
if sys.platform == "win32":
    import ctypes
    import time as _time

    _MUTEX_NAME = "KototsunaAppMutex"
    _WINDOW_TITLE = "ことつな！"

    _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, _MUTEX_NAME)
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        # 既存インスタンスのウィンドウを確認
        _hwnd = ctypes.windll.user32.FindWindowW(None, _WINDOW_TITLE)
        if _hwnd:
            # 正常な既存インスタンス → フォアグラウンドに出してexit
            ctypes.windll.user32.ShowWindow(_hwnd, 9)   # SW_RESTORE
            ctypes.windll.user32.SetForegroundWindow(_hwnd)
            sys.exit(0)
        elif getattr(sys, 'frozen', False):
            # ゾンビプロセス（ウィンドウなし）→ 強制終了して起動を継続
            import subprocess as _subprocess
            _my_pid = os.getpid()
            try:
                _result = _subprocess.run(
                    ['tasklist', '/FI', 'IMAGENAME eq Kototsuna.exe', '/FO', 'CSV', '/NH'],
                    capture_output=True, text=True, timeout=3
                )
                for _line in _result.stdout.strip().splitlines():
                    _parts = [p.strip('"') for p in _line.split('","')]
                    if len(_parts) > 1:
                        try:
                            _pid = int(_parts[1])
                            if _pid != _my_pid:
                                _subprocess.run(
                                    ['taskkill', '/F', '/PID', str(_pid)],
                                    capture_output=True, timeout=3
                                )
                        except (ValueError, IndexError):
                            pass
            except Exception:
                pass
            # ハンドルを解放し、旧プロセス終了を待ってMutexを再取得
            ctypes.windll.kernel32.CloseHandle(_mutex)
            for _retry in range(5):
                _time.sleep(0.3)
                _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, _MUTEX_NAME)
                if ctypes.windll.kernel32.GetLastError() != 183:
                    break  # 再取得成功
                ctypes.windll.kernel32.CloseHandle(_mutex)
            else:
                sys.exit(0)  # 再取得失敗 → 起動を諦める
        else:
            sys.exit(0)

# PyInstaller GUIモードでのクラッシュログ記録（console=Falseではトレースバックが見えないため）
# rthookで設置済みのraw excepthookを上書きし、可能ならtraceback moduleで詳細出力する。
# 失敗時はraw方式（osモジュールのみ）にフォールバック。
if getattr(sys, 'frozen', False):
    def _kototsuna_excepthook(exc_type, exc_value, exc_tb):
        # exeの隣にエラーログを出力（ユーザーが見つけやすい）
        _exe_dir = os.path.dirname(sys.executable) if hasattr(sys, 'executable') and sys.executable else ''
        if _exe_dir:
            try:
                _test = os.path.join(_exe_dir, '.kototsuna_write_test')
                _tfd = os.open(_test, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
                os.close(_tfd)
                os.unlink(_test)
            except OSError:
                _exe_dir = ''
        _err_path = os.path.join(
            _exe_dir or os.environ.get('TEMP', os.environ.get('TMP', '.')),
            'kototsuna_error.txt'
        )
        _written = False
        # 方法1: traceback module使用（詳細なトレースバック）
        try:
            import traceback
            with open(_err_path, 'w', encoding='utf-8') as f:
                traceback.print_exception(exc_type, exc_value, exc_tb, file=f)
            _written = True
        except Exception:
            pass
        # 方法2: raw方式フォールバック（osモジュールのみ、base_library.zip不要）
        if not _written:
            try:
                _lines = [f"exc_type={exc_type}", f"exc_value={exc_value}", "traceback:"]
                _tb = exc_tb
                while _tb is not None:
                    _frame = _tb.tb_frame
                    _code = _frame.f_code
                    _lines.append(f"  File \"{_code.co_filename}\", line {_tb.tb_lineno}, in {_code.co_name}")
                    _tb = _tb.tb_next
                _text = '\n'.join(_lines) + '\n'
                _fd = os.open(_err_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
                os.write(_fd, _text.encode('utf-8', errors='replace'))
                os.close(_fd)
            except Exception:
                pass
        # 最小限のシステム情報をkototsuna_diag.txtに記録（次回起動時のZIP収集用マーカー）
        # os/sys/platformのみ使用（AV隔離下でも動作するよう依存を最小化）
        try:
            import platform as _platform
            _diag_path = os.path.join(
                _exe_dir or os.environ.get('TEMP', os.environ.get('TMP', '.')),
                'kototsuna_diag.txt'
            )
            _diag_lines = [
                f"crashed_at={_time.strftime('%Y-%m-%dT%H:%M:%S')}",
                f"exc_type={exc_type.__name__ if exc_type else 'unknown'}",
                f"exc_value={str(exc_value)[:200]}",
                f"platform={_platform.platform()}",
                f"python={sys.version.split()[0]}",
                f"executable={sys.executable}",
            ]
            _diag_text = '\n'.join(_diag_lines) + '\n'
            _dfd = os.open(_diag_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
            os.write(_dfd, _diag_text.encode('utf-8', errors='replace'))
            os.close(_dfd)
        except Exception:
            pass
        # stderrへの出力も試行
        try:
            sys.__excepthook__(exc_type, exc_value, exc_tb)
        except Exception:
            pass
    sys.excepthook = _kototsuna_excepthook

# PyInstaller: 旧_MEIPASSのSSL証明書パスを現在の_MEIPASSに修正
# アップデート後の再起動で旧パスが環境変数に残り、TLSエラーになる対策
if getattr(sys, 'frozen', False):
    _meipass = getattr(sys, '_MEIPASS', '')
    if _meipass:
        _cert = os.path.join(_meipass, 'certifi', 'cacert.pem')
        if os.path.exists(_cert):
            os.environ['SSL_CERT_FILE'] = _cert
            os.environ['REQUESTS_CA_BUNDLE'] = _cert

# コンソールウィンドウを非表示（console=True + hide-early のバックアップ）
if sys.platform == "win32" and getattr(sys, 'frozen', False):
    try:
        import ctypes
        _hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if _hwnd:
            ctypes.windll.user32.ShowWindow(_hwnd, 0)  # SW_HIDE
        ctypes.windll.kernel32.FreeConsole()  # プロセスからコンソールを完全切り離し
    except Exception:
        pass

# PyInstallerでの相対パス解決用にsrcをパスへ追加
BASE_DIR = getattr(sys, "_MEIPASS", os.path.abspath(os.path.dirname(__file__)))
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

def configure_tcl_tk_paths() -> None:
    """PyInstaller onefile環境でTcl/Tkパスを補正する。"""
    tcl_candidates = [
        os.path.join(BASE_DIR, "_tcl_data"),
        os.path.join(BASE_DIR, "_tcl_data", "tcl8.6"),
        os.path.join(BASE_DIR, "_internal", "_tcl_data"),
        os.path.join(BASE_DIR, "_internal", "_tcl_data", "tcl8.6"),
        os.path.join(BASE_DIR, "tcl", "tcl8.6"),
    ]
    tk_candidates = [
        os.path.join(BASE_DIR, "_tk_data"),
        os.path.join(BASE_DIR, "_tk_data", "tk8.6"),
        os.path.join(BASE_DIR, "_internal", "_tk_data"),
        os.path.join(BASE_DIR, "_internal", "_tk_data", "tk8.6"),
        os.path.join(BASE_DIR, "tcl", "tk8.6"),
    ]

    def _pick_with_file(candidates, filename):
        for path in candidates:
            if os.path.isfile(os.path.join(path, filename)):
                return path
        return ""

    tcl_path = _pick_with_file(tcl_candidates, "init.tcl")
    tk_path = _pick_with_file(tk_candidates, "tk.tcl")

    if not tcl_path or not tk_path:
        for root, dirs, files in os.walk(BASE_DIR):
            if not tcl_path and "init.tcl" in files:
                tcl_path = root
            if not tk_path and "tk.tcl" in files:
                tk_path = root
            if tcl_path and tk_path:
                break

    if tcl_path:
        os.environ["TCL_LIBRARY"] = tcl_path
    if tk_path:
        os.environ["TK_LIBRARY"] = tk_path


configure_tcl_tk_paths()

# PyInstaller GUIモード(console=False)ではstdout/stderrがNoneになる
# customtkinter等がwrite()を試みるとAttributeErrorになるため、devnullにリダイレクト
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')

import tkinter as tk
from dotenv import load_dotenv

# concurrent.futures を事前インポート（遅延インポート時のPyInstallerアーカイブ再読込を回避）
# BOTスレッドでasyncio.run_in_executor()が呼ばれた際、AVによる.exeロック下で
# PyInstallerが.exeからバイトコード抽出に失敗する問題の対策
import concurrent.futures  # noqa: F401

# ロガーを最初にインポート（他のモジュールより先に初期化）
from src.logger import logger  # noqa: E402

# Sentry はオプトイン同意済みのときだけ起動。同意なしまたは SDK 欠落時は no-op。
# 起点をできるだけ早くするため、heavy import の前に呼ぶ。
try:
    from src.config import load_config as _load_config_for_sentry  # noqa: E402
    from src.sentry_init import init_sentry as _init_sentry  # noqa: E402
    _init_sentry(bool(_load_config_for_sentry().get("telemetry_crash_reporting", False)))
except Exception:
    # 設定読み込みやSentry初期化に失敗しても本体起動は止めない
    pass

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
        # AV隔離で_MEIのアイコンが消失した場合、runtime_cacheからフォールバック
        if not os.path.exists(icon_path):
            _rc = os.environ.get('KOTOTSUNA_RUNTIME_CACHE', '')
            if _rc:
                icon_path = os.path.join(_rc, "assets", "icon.png")
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

def _show_safe_mode_dialog(master, crash_count: int) -> tuple[bool, bool]:
    """セーフモード確認ダイアログを表示する。

    Returns:
        (safe_mode: bool, reset_config: bool)
    """
    result: dict[str, bool] = {"safe_mode": True, "reset_config": False}

    dialog = ctk.CTkToplevel(master)
    dialog.title("起動エラーを検出")
    dialog.resizable(False, False)
    dialog.attributes("-topmost", True)
    dialog.grab_set()

    w, h = 500, 340
    dialog.update_idletasks()
    x = (dialog.winfo_screenwidth() - w) // 2
    y = (dialog.winfo_screenheight() - h) // 2
    dialog.geometry(f"{w}x{h}+{x}+{y}")

    ctk.CTkLabel(
        dialog,
        text="⚠️  起動エラーを検出しました",
        font=("Segoe UI", 15, "bold"),
        text_color="#EAB308",
    ).pack(pady=(24, 6))

    ctk.CTkLabel(
        dialog,
        text=(
            f"直近の起動が {crash_count} 回連続で失敗しています。\n"
            "セーフモードで起動すると、問題を引き起こす可能性のある\n"
            "機能を無効化してアプリを安定した状態で起動できます。"
        ),
        font=("Segoe UI", 11),
        justify="center",
        wraplength=440,
    ).pack(pady=6)

    ctk.CTkLabel(
        dialog,
        text="セーフモードで無効化: OBS自動起動・VOICEVOX自動起動・自動アップデート確認",
        font=("Segoe UI", 10),
        text_color="#9BAEC6",
        wraplength=460,
    ).pack(pady=4)

    def on_safe_mode() -> None:
        result["safe_mode"] = True
        result["reset_config"] = False
        dialog.destroy()

    def on_normal() -> None:
        result["safe_mode"] = False
        result["reset_config"] = False
        dialog.destroy()

    def on_reset() -> None:
        result["safe_mode"] = True
        result["reset_config"] = True
        dialog.destroy()

    btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
    btn_frame.pack(pady=20, fill="x", padx=20)

    ctk.CTkButton(
        btn_frame,
        text="🛡️ セーフモードで起動",
        command=on_safe_mode,
        fg_color="#2563EB",
        hover_color="#1D4ED8",
        width=160,
    ).pack(side="left", expand=True, padx=4)

    ctk.CTkButton(
        btn_frame,
        text="▶ 通常起動",
        command=on_normal,
        fg_color="#374151",
        hover_color="#4B5563",
        width=130,
    ).pack(side="left", expand=True, padx=4)

    ctk.CTkButton(
        btn_frame,
        text="🔄 設定リセット",
        command=on_reset,
        fg_color="#DC2626",
        hover_color="#B91C1C",
        width=130,
    ).pack(side="left", expand=True, padx=4)

    dialog.wait_window()
    return result["safe_mode"], result["reset_config"]


def _show_post_update_recovery_dialog(master, crash_count: int, previous_version: str) -> str:
    """アップデート直後の連続クラッシュ時に復旧方法を確認する。"""
    result = messagebox.askyesnocancel(
        "アップデート後の起動失敗を検出",
        (
            f"アップデート後の起動が {crash_count} 回連続で失敗しています。\n\n"
            f"「はい」: 前のバージョン ({previous_version}) に戻す\n"
            "「いいえ」: セーフモードで起動する\n"
            "「キャンセル」: 通常起動を試す"
        ),
        parent=master,
    )
    if result is True:
        return "rollback"
    if result is False:
        return "safe_mode"
    return "normal"


if __name__ == '__main__':
    # 前回アップデート後のクリーンアップ
    if "--cleanup" in sys.argv:
        import time
        time.sleep(2)
        from src.updater import cleanup_old_exe
        cleanup_old_exe()

    # 起動を記録（クラッシュカウンタ増加）
    from src.safe_mode import (
        record_startup,
        reset_crash_count,
        should_offer_post_update_rollback,
        should_suggest_safe_mode,
        collect_crash_diagnostics,
    )
    _crash_count = record_startup()

    # クラッシュ後の初回起動時に診断バンドルを自動収集
    _diag_bundle_path = None
    if _crash_count > 0:
        _diag_bundle_path = collect_crash_diagnostics()

    # アップデート直後かどうか確認
    from src.config import load_config as _load_config
    from src.updater import UpdateError, get_rollback_info, rollback_to_previous
    _startup_config = _load_config()
    _just_updated = _startup_config.get("just_updated", False)
    _rollback_info = get_rollback_info() if _just_updated else None

    # セーフモード状態
    _safe_mode_active = False
    _startup_recovery_handled = False

    # メインウィンドウを作成（非表示）
    try:
        root = ctk.CTk()
    except Exception:
        raise
    root.withdraw()  # 最初は非表示

    # アップデート直後の連続クラッシュ時は、通常初期化前にロールバックを提案する
    if should_offer_post_update_rollback(
        _crash_count,
        _just_updated,
        bool(_rollback_info and _rollback_info.get("version")),
    ):
        action = _show_post_update_recovery_dialog(
            root,
            _crash_count,
            _rollback_info["version"],
        )
        _startup_recovery_handled = True

        if action == "rollback":
            try:
                rollback_to_previous()
                sys.exit(0)
            except UpdateError as e:
                logger.error(f"起動前ロールバック失敗: {e}")
                messagebox.showerror(
                    "ロールバックエラー",
                    f"前のバージョンに戻せませんでした:\n{e}",
                    parent=root,
                )
                _startup_recovery_handled = False
            except Exception as e:
                logger.error(f"起動前ロールバック中の予期しないエラー: {e}", exc_info=True)
                messagebox.showerror(
                    "ロールバックエラー",
                    f"前のバージョンに戻せませんでした:\n{e}",
                    parent=root,
                )
                _startup_recovery_handled = False
        elif action == "safe_mode":
            _safe_mode_active = True

    # セーフモード確認（クラッシュ閾値超過時はスプラッシュより先に表示）
    if not _startup_recovery_handled and should_suggest_safe_mode(_crash_count):
        _safe_mode_active, _reset_config = _show_safe_mode_dialog(root, _crash_count)
        if _reset_config:
            from src.config import reset_config as _reset_cfg
            _reset_cfg()
            logger.info("設定をデフォルトにリセットしました（セーフモード要求）")

    # スプラッシュスクリーンを表示
    splash = create_splash_screen()

    # メインアプリを初期化
    def init_app():
        global app
        try:
            app = KototsunaApp(root, safe_mode=_safe_mode_active, diag_bundle_path=_diag_bundle_path)
            # ウィンドウを閉じる際のプロトコルを設定
            root.protocol("WM_DELETE_WINDOW", on_closing)
            # スプラッシュスクリーンを閉じる
            splash.destroy()
            # メインウィンドウを表示
            root.deiconify()
            # 正常起動 → クラッシュカウンタをリセット
            reset_crash_count()
            # アップデート直後ならチャットログに通知
            if _just_updated:
                root.after(500, app._show_update_notification)
        except Exception as e:
            logger.critical(f"アプリケーション初期化エラー: {e}", exc_info=True)
            splash.destroy()
            root.destroy()

    # スプラッシュ描画後にメインアプリを初期化
    root.after(100, init_app)
    root.mainloop()
