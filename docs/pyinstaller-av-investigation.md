# PyInstaller AV隔離 + Import順序問題 調査報告書

## 1. 問題の概要

Kototsuna（PyInstaller onefile, Python 3.12, Windows）が以下の2つの問題を抱えている：

1. **初回起動失敗**: Windows Defenderが`_MEI*`内の`base_library.zip`を隔離
2. **import順序破壊**: rthook修正でshutil/tempfileのimportを除去した結果、`collections.abc.Hashable`が消失

## 2. 全バージョン修正履歴

### Tcl/Tk問題期（v1.1.3〜v1.1.5）

| Ver | 修正内容 | 結果 |
|-----|---------|------|
| v1.1.3 + rc1〜rc12 | Tcl/Tkデータを個別ファイルとして収集 | PyInstallerのdatasパイプラインで`init.tcl`消失。12回RC全失敗 |
| v1.1.4 | 空の`hook-_tkinter.py`で標準hookオーバーライド | init.tcl消失は解消されず |
| v1.1.5 | Tcl/TkをZIPバンドル+rthookで展開 | init.tcl問題を解決 |

### 診断・AV対策期（v1.1.6〜v1.1.9）

| Ver | 修正内容 | 結果 |
|-----|---------|------|
| v1.1.6 | rthookに詳細診断出力を追加 | 診断のみ |
| v1.1.7 | rthook診断にcustomtkinterパス確認追加 | 診断のみ |
| v1.1.8 | `runtime_tmpdir='.'`（exe隣に展開）| AV回避効果不安定 |
| v1.1.9 | ファイルプリキャッシュ+`builtins.open()`ラッパー | blue.json AV隔離を解決 |

### base_library.zip問題期（v1.2.0〜v1.2.4）

| Ver | 修正内容 | 結果 |
|-----|---------|------|
| v1.2.0 | `excepthook`でクラッシュログをファイル出力 | エラー可視化 |
| v1.2.1 | `console=False`でstdout/stderr=None→devnull | stdout問題解決 |
| v1.2.2 | `runtime_tmpdir='.'`を復元 | 効果不安定、削除済み |
| v1.2.3 | base_library.zipを`%LOCALAPPDATA%`にコピー | 削除済み |
| v1.2.4 | キャッシュ削除を大文字小文字無視で走査 | 削除済み |

### チャットコマンド + AV防御強化期（v1.3.0〜v1.3.3）

| Ver | 修正内容 | 結果 |
|-----|---------|------|
| **v1.3.0** | チャットコマンド機能追加 | **動作する唯一の安定版**。初回起動NG、二回目OK |
| v1.3.1（初） | 3層AV防御に強化 | 起動不能、削除済み |
| v1.3.2 | rthookからshutil/tempfileのimportを除去（deferred import導入） | 起動不能、削除済み |
| v1.3.3 | raw excepthook追加 | 起動不能、削除済み |
| v1.3.1（2回目） | AV隔離対策rthook改善 | 起動不能、削除済み |

### RC期（v1.3.1-rc1〜rc5）

| Ver | 修正内容 | 結果 |
|-----|---------|------|
| v1.3.1-rc1 | エラーログexe隣出力・TOCTOU修正 | `collections.abc.Hashable`消失 |
| v1.3.1-rc2 | _MEI正常時パス差し替えスキップ | 同上（_SafeBaseLibFinder残存） |
| v1.3.1-rc3 | _SafeBaseLibFinderもスキップ | 同上（deferred importが根本原因） |
| v1.3.1-rc4 | ハイブリッドimport + `_prime_collections_abc_binding()` | **collections.abc解決**。AV遅延隔離でbase_library.zip消失（TOCTOU） |
| v1.3.1-rc5 | sys.pathを常にsafe_baseへ切り替え | staleなimporter cache残存（collections.__path__経由で再生成） |
| v1.3.1-rc6 | B-5復活（__path__/__spec__書き換え）+ 最終キャッシュ掃除 | **base_library.zip問題完全解決**。別問題（pyaudio._portaudio欠落）発覚 |
| v1.3.1-rc7 | `pyaudio._portaudio`をhiddenimportsに明示追加 | 効果なし（hiddenimportsだけでは.pydが収集されない） |
| v1.3.1-rc8 | `.pyd`を明示的にbinariesへ追加 + collect_all診断出力 | バンドルは成功したがAV隔離で初回起動時に`_portaudio.pyd`消失 |
| v1.3.1-rc9 | `.pyd`をruntime_cacheにプリキャッシュ + meta_path finderで迂回 | finderが`_portaudio.pyd`をハードコードしていたが実ファイル名は`_portaudio.cp312-win_amd64.pyd` |
| v1.3.1-rc10 | finderをキャッシュ時に記録した実パスで参照するよう修正 | `pyaudio._portaudio`解決。次は`PIL._imaging`が同じ問題で発覚 |
| v1.3.1-rc11 | 全`.pyd`を汎用的にruntime_cacheへプリキャッシュ + 汎用finder | `.pyd` import解決。`pygame`ディレクトリごとAV隔離で`os.add_dll_directory`失敗 |
| v1.3.1-rc12 | `.dll`もプリキャッシュ + `os.add_dll_directory`パッチ + 古`_MEI`自動削除 | 237 DLLコピーに時間がかかり、その間にAVがtcl_tk_data.zip等を隔離 |
| v1.3.1-rc13 | 重要データファイルをos.walkループ前に最優先コピー + Phase1/2にruntime_cacheフォールバック | Tcl/Tkデータ解決。`_tkinter.pyd`のDLL依存（tcl86t.dll等）がトップレベルDLL除外により解決不能 |
| v1.3.1-rc14 | トップレベルDLL含む全DLLキャッシュ + pyd_cache_rootをDLL検索パス登録 + サイズベースのスキップ最適化 | `_tkinter` DLLロード解決。`init.tcl`がAV隔離で消失（TCL_LIBRARYが_MEI指向のため） |
| v1.3.1-rc15 | tcl_tk_data.zipをruntime_cacheにも展開 + TCL_LIBRARY/TK_LIBRARYをruntime_cache優先に変更 | TCL_LIBRARYは正しく設定されたが、PyInstaller組み込み`pyi_rth__tkinter.py`がAV隔離された`_MEI/_tcl_data`チェックでクラッシュ |
| v1.3.1-rc16 | `os.path.isdir`パッチ（_MEI Tcl/Tkディレクトリ偽装）+ `os.environ`書き込みブロック（TCL_LIBRARY/TK_LIBRARY保護） | 起動成功。アイコン・画像がAV隔離で表示されない |
| v1.3.1-rc17 | アセットファイルをruntime_cacheにプリキャッシュ + main.py/gui.pyにruntime_cacheフォールバック追加 | 初回起動クラッシュ解決。「Failed to remove temporary directory」警告が残存 |
| v1.3.1-rc18 | `runtime_tmpdir=None`で親子プロセスモード復帰 + exe隣の旧_MEI残骸クリーンアップ | テスト中 |

## 3. 根本原因の詳細分析

### 3.1 `collections.abc.Hashable`消失のメカニズム

**クラッシュチェーン：**
```
pyi_rth_pyqt6.py → PyQt6.__init__ → pkgutil → functools.singledispatch.register()
→ functools._is_union_type() → import typing → typing.py line ~2540:
    Hashable = _alias(collections.abc.Hashable, 0)
→ AttributeError: module 'collections.abc' has no attribute 'Hashable'
```

**CPython 3.12 typing.pyの該当コード（line 2540〜2605）：**
```python
Hashable = _alias(collections.abc.Hashable, 0)
Awaitable = _alias(collections.abc.Awaitable, 1)
Coroutine = _alias(collections.abc.Coroutine, 3)
# ... 約20個のcollections.abc属性アクセス
```

### 3.2 v1.3.0（動作版）とrc系（壊れた版）の違い

```python
# v1.3.0（動作する）
import os, sys, zipfile, shutil, tempfile, builtins, io, zipimport
# ↑ shutilがcollections.abcを、tempfileがfunctoolsを完全初期化

# rc系（壊れる）
import os, sys, builtins, zipimport  # 最小限のみ
# shutil/tempfileは未import → collections.abc未初期化
```

**なぜshutilのimportが重要か：**
- `import shutil` → 内部で `import collections.abc` が実行される
- `_collections_abc`はCPythonのfrozenモジュール（C実装、base_library.zip不要）
- しかし `collections.abc`（Pythonラッパー）の初期化と`collections`パッケージへのバインディングが必要
- shutil import時にこのバインディングが確立される
- その後、import cacheを操作しても、既にメモリ上のPythonオブジェクトとして確立されたバインディングは壊れない

### 3.3 PyInstaller base_library.zipの構成

`PY3_BASE_MODULES`に含まれるモジュール（base_library.zip内）：
```
_collections_abc, abc, codecs, collections, copyreg, encodings, enum,
functools, genericpath, heapq, io, keyword, linecache, locale, ntpath,
operator, os, posixpath, re, reprlib, sre_compile, sre_constants,
sre_parse, stat, traceback, types, weakref, warnings
```

**typingはbase_library.zipに含まれない** → PYZアーカイブ（_MEI*内）から読み込まれる。

### 3.4 AV隔離の根本原因

PyInstaller 6.xのbootloaderバイナリは全ユーザー共通のため、マルウェアと同じシグネチャを持つ：
- PyInstaller 5.13.2: VirusTotal 2/69検出
- PyInstaller 6.3.0: VirusTotal 6/69検出（Microsoft Defender含む）
- PyInstaller 6.x全般: 15-18のAVベンダーが検出

PyInstaller開発チームは Issue #8164 を「Not Planned」でクローズ（「我々は完全に無力」）。

## 4. 解決策の比較

### Approach A: v1.3.0ベース最小変更

```python
# rthookのトップレベルでshutil/tempfileを含む全モジュールをimport
import os, sys, zipfile, shutil, tempfile, builtins, io, zipimport
# Phase 0: shutil.copy2でバックアップ → sys.path差し替え
```

| 項目 | 評価 |
|------|------|
| 実装コスト | 極小 |
| 通常起動 | 安定（v1.3.0実績） |
| AV隔離時 | rthook自体が`import shutil`で即死 |
| 2回目起動 | 安定（runtime_cache） |
| リスク | 低 |

### Approach B: ハイブリッドimport + collections.abc明示バインディング（推奨）

```python
import os, sys, builtins, zipimport

_has_stdlib = False
try:
    import shutil, tempfile, io as _io, zipfile
    _has_stdlib = True
except Exception:
    zipfile = shutil = tempfile = _io = None

# _has_stdlib=True → v1.3.0と同じフルコピー戦略
# _has_stdlib=False → os/builtinsのみでruntime_cache利用

def _prime_collections_abc_binding():
    __import__('_collections_abc')  # frozen module
    c = __import__('collections', fromlist=['abc'])
    cabc = __import__('collections.abc', fromlist=['Hashable'])
    if getattr(c, 'abc', None) is not cabc:
        setattr(c, 'abc', cabc)
    assert hasattr(cabc, 'Hashable')
```

| 項目 | 評価 |
|------|------|
| 実装コスト | 中 |
| 通常起動 | 安定（通常モード=A同等） |
| AV隔離時 | フォールバックで復旧試行 |
| 2回目起動 | 安定 |
| リスク | 低〜中（フォールバック分岐の検証は必要） |

### Approach C: 根本原因排除

| 方法 | コスト | 効果 | 備考 |
|------|--------|------|------|
| onedirモード | 大 | AV問題消滅 | updater大幅改修必要 |
| Azure Trusted Signing | 月$9.99 | AV問題大幅減少 | CI/CD統合必要 |
| bootloaderソースビルド | 中 | AV誤検出減少 | 効果は限定的 |
| MSIX パッケージング | 中 | AV問題消滅 | 自己署名証明書でOK |
| _MEIプレフィックス変更 | 小 | AV誤検出減少 | bootloader改変必要 |

## 5. 実装の経緯と教訓

### 5.1 rc4: collections.abc問題の解決

**修正内容:**
- ハイブリッドimport: `try/except`でshutil/tempfileを早期import（通常時v1.3.0互換）
- `_prime_collections_abc_binding()`: `_collections_abc`(frozen) → `collections` → `collections.abc`の3段階importで親属性を明示バインド
- `__spec__/__path__`書き換え削除: モジュール内部状態破壊のリスク排除
- `_SafeBaseLibFinder`(meta_path)削除: PYZ解決との競合リスク排除

**結果:**
- `collections_abc=OK` → Hashable問題は完全解決
- しかし`relocation=SKIPPED(mei_ok)`により、rthook完了後のAV遅延隔離で`base_library.zip`が消失
- エラー: `pyi_rth_inspect.py` → `inspect.py` → `zipimport`が`_MEI*/base_library.zip`を読めない

**教訓:**
- AV隔離はrthook実行中だけでなく、完了後にも発生する（TOCTOU問題）
- `_MEI`が正常かどうかのチェックは時間的に意味がない

### 5.2 rc5: TOCTOU対策（常時パス差し替え）

**修正内容:**
- `_need_relocation = not _copied`（条件付き）を廃止
- safe_baseが存在すれば常にsys.path / importer cacheを切り替え
- `_prime_collections_abc_binding()`がバインディング破壊を防止するため安全

**期待される動作:**
```
通常起動:
  early_stdlib_import=OK → copied_from_mei → sys.path→safe_base
  → _prime_collections_abc_binding() → collections_abc=OK
  → 後続フック: safe_baseからimport → 成功

AV隔離時:
  early_stdlib_import=FAIL → mei_copy_failed → using_prestaged_copy
  → sys.path→safe_base → post_phase0_stdlib_import=OK
  → _prime_collections_abc_binding() → collections_abc=OK
  → 後続フック: safe_baseからimport → 成功
```

### 5.3 rc6: staleキャッシュ問題の解決

**発生した問題:**
- rc5の診断で`pic_now`に`_MEI\base_library.zip\collections`と`_MEI\base_library.zip\encodings`が残存
- `import shutil`時に`collections.__path__`が`_MEI`パスで設定される
- B-2でキャッシュをクリアしても、`_prime_collections_abc_binding()`が`collections.abc`をimportする際に古い`__path__`経由でstaleなキャッシュが再生成される

**修正内容:**
- **B-5復活**: `sys.modules`内の全パッケージの`__path__`と`__spec__`を走査し、`_MEI`パスを`safe_base`に書き換え
- **最終キャッシュ掃除**: `_prime_collections_abc_binding()`完了後に再度`sys.path_importer_cache`からstaleエントリを除去

**結果:**
- `modules_fixed=3`: 3モジュールの`__path__`を修正
- `final_cache_cleaned=0`: B-5が完全に機能し、最終掃除で残存エントリなし
- 全`pic_now`が`safe_base`（`AppData\Local\Kototsuna\runtime_cache`）を指向
- **base_library.zip / AV隔離 / collections.abc問題チェーンが完全解決**

**教訓:**
- `sys.path`と`sys.path_importer_cache`の修正だけでは不十分。既にロードされたモジュールの`__path__`属性がキャッシュの再汚染源になる
- キャッシュクリア→import→再クリアの2段構えが必要

### 5.4 rc7/rc8: pyaudio._portaudio欠落（別問題）

**発生した問題:**
- base_library.zip関連の問題はrc6で完全解決
- 新たに`ModuleNotFoundError: No module named 'pyaudio._portaudio'`が発生
- `_portaudio`はCエクステンション（`.pyd`）で、`collect_all('pyaudio')`で漏れる場合がある
- rc6以前のRCではbase_library.zip問題で先にクラッシュしていたため、この問題は潜在していた

**rc7の試み（効果なし）:**
- `hiddenimports += ['pyaudio._portaudio']`を追加
- CIビルドログに`_portaudio`関連のWARNINGなし → `hiddenimports`だけではCエクステンション（.pyd）のバンドルに不十分

**rc8の修正内容:**
- `collect_all('pyaudio')`の返り値（datas/binaries/hiddenimports件数）をビルドログに出力して診断
- `pyaudio/`ディレクトリから`_portaudio*.pyd`を直接`binaries`リストに明示追加
- 3段防御: `collect_all` + `hiddenimports` + 明示的`binaries`追加

**rc8の結果:**
- ビルドは成功し、`_portaudio.pyd`は`_MEI*`に正しくバンドルされた
- しかし初回起動時にAV（Windows Defender）が`_portaudio.pyd`を隔離 → `ModuleNotFoundError`
- 二回目起動では`_MEI*`が残存しており、AV解除済みで成功
- **根本原因はbase_library.zipと同じ: AV遅延隔離によるファイル消失**

### 5.5 rc9: _portaudio.pyd AV隔離対策

**修正内容:**
- **Phase 0.5**: rthookにCエクステンションのプリキャッシュを追加。`_MEI*/pyaudio/_portaudio.pyd`を`runtime_cache/pyaudio/_portaudio.pyd`にコピー（`builtins.open`のみ使用、stdlib不要）
- **Phase 0.5b**: `sys.meta_path`の先頭に`_SafePydFinder`を挿入。`pyaudio._portaudio`のimportを常に`runtime_cache`から読み込み
- base_library.zipと同じ戦略: AV隔離前にコピーし、常にsafe copyを使用（TOCTOU回避）

**技術詳細:**
- `_SafePydFinder.find_spec()`: `importlib.util.spec_from_file_location()`でCエクステンションのModuleSpecを生成
- `sys.meta_path[0]`に挿入することで、PyInstallerのFrozenImporterより先に評価
- DLL依存: PyInstallerが`_MEI*`を`os.add_dll_directory()`で登録済みのため、`runtime_cache`からの`.pyd`ロードでもDLL依存は解決される

**rc9の結果（失敗）:**
- プリキャッシュ: `cached:_portaudio.cp312-win_amd64.pyd` → **成功**
- finder: `finder=installed`, `meta_path[0]=_SafePydFinder` → **インストール成功**
- しかし`find_spec()`内で`_portaudio.pyd`をハードコード検索していたため、実ファイル名`_portaudio.cp312-win_amd64.pyd`にマッチせずfinderが空振り
- Python 3.12のCエクステンションは`{name}.cp{ver}-{platform}.pyd`形式のファイル名を使用

### 5.6 rc10: finderファイル名修正

**修正内容:**
- Phase 0.5でキャッシュ成功時に`_portaudio_safe_path`に実パスを記録
- Phase 0.5bのfinder内でハードコードファイル名を廃止し、記録済みの実パスを直接参照
- 診断出力に`portaudio_safe_path`を追加

**rc10の結果:**
- `pyaudio._portaudio`は解決（`portaudio_safe_path`が正しく記録され、finderが正常に動作）
- しかし`PIL._imaging`が同じパターンで発覚: `ImportError: cannot import name '_imaging' from 'PIL'`
- パッケージ個別対応（whack-a-mole）では追いつかない → 汎用化が必要

### 5.7 rc11: 全Cエクステンション汎用プリキャッシュ

**修正内容:**
- **Phase 0.5を汎用化**: `_MEI*`内の全`.pyd`/`.so`ファイルを`os.walk`で走査し、`runtime_cache/pyd_cache/`に構造ごとコピー
- **Phase 0.5bを汎用化**: `_pyd_safe_map`（fullname→safe_path辞書）を参照する汎用`_SafePydFinder`
- パッケージ個別のハードコード（`pyaudio._portaudio`、`PIL._imaging`等）を一切排除

**技術詳細:**
- `os.walk(_meipass)`で全サブディレクトリの`.pyd`/`.so`を発見
- ファイル名からモジュール名を算出: `PIL/_imaging.cp312-win_amd64.pyd` → `PIL._imaging`
- `_pyd_safe_map = {fullname: safe_path}` に全エントリを登録
- finderは辞書lookupのみ（O(1)）で高速

**教訓:**
- AV隔離はどの`.pyd`ファイルにも発生しうる — パッケージ固定の対処は持続不可能
- `os.walk` + 汎用finderで全Cエクステンションを一括保護するのが正解
- `collect_all()`はPythonモジュールを網羅的に収集するが、Cエクステンション（.pyd/.so）は漏れることがある
- **バンドルだけでは不十分**: `.pyd`がバンドルに含まれていても、AV隔離で実行時に消失する
- **ファイル名をハードコードしてはいけない**: Python 3.12では`{name}.cp312-win_amd64.pyd`形式
- base_library.zipで確立した「runtime_cacheプリキャッシュ + import迂回」パターンはCエクステンションにも汎用適用可能

**rc11の結果:**
- `pyd_safe_map_size=76`（76個の.pydをキャッシュ成功） → `.pyd` importは全て解決
- 新たに`pygame/__init__.py`がline 38で`os.add_dll_directory(_MEI*/pygame)`を呼び出し、AV隔離でディレクトリごと消失 → `FileNotFoundError: [WinError 2]`
- `.pyd`のimport問題とは異なる: DLLのロードパス登録の問題

### 5.8 rc12: DLLキャッシュ + os.add_dll_directoryパッチ

**修正内容:**
- **Phase 0.5拡張**: `.pyd`/`.so`に加え、パッケージサブディレクトリ内の`.dll`ファイルもruntime_cacheにコピー（トップレベルDLLは除外: サイズが大きく隔離リスクが低い）
- **Phase 0.5c**: `os.add_dll_directory`をモンキーパッチ。`_MEI`パスが`FileNotFoundError`になった場合、`runtime_cache/pyd_cache/`の同等パスにフォールバック
- **Phase 2.5**: 古い`_MEI*`ディレクトリの自動削除を追加

**技術詳細:**
- `os.add_dll_directory`はWindows API `AddDllDirectory`のラッパー。ディレクトリが存在しないとWinError 2で失敗
- `os.path.relpath(path, _meipass)`でMEI相対パスを算出し、`pyd_cache`内の対応ディレクトリを検索
- DLLサブディレクトリ内のSDL2.dll等も事前コピーされているため、フォールバック先に実体がある

**教訓:**
- AV隔離は`.pyd`ファイルだけでなく、パッケージディレクトリ全体に及ぶ場合がある
- `os.add_dll_directory`もAV隔離の影響を受ける — ネイティブDLLのロードパス登録も防御が必要
- 防御すべき層: (1) base_library.zip (2) .pyd import (3) DLLロードパス — 全層でruntime_cacheフォールバックが必要

**rc12の結果:**
- `pyd_cached=76`, `dll_cached=237`, `finder=installed`, `dll_dir_patched=YES` — 防御機構は全て成功
- しかし237 DLLのコピーに時間がかかり、その間にAVが`tcl_tk_data.zip`とテーマJSONを隔離
- `cached_files_count=0`（テーマJSON読み込み失敗）、`init_tcl_exists=False`（Tcl/Tk未展開）
- PyInstallerの`pyi_rth__tkinter.py`が`_tcl_data`ディレクトリ不在で`FileNotFoundError`

### 5.9 rc13: 重要データファイルの最優先コピー

**修正内容:**
- **Phase 0.5先頭**: `os.walk`ループの前に`tcl_tk_data.zip`、`blue.json`、`green.json`をruntime_cacheに最優先コピー
- **Phase 1改善**: テーマJSON読み込みに`runtime_cache`フォールバック追加（_MEIから読めない場合はキャッシュから読む）
- **Phase 2改善**: `tcl_tk_data.zip`が_MEIにない場合、`runtime_cache`のコピーから展開

**教訓:**
- バイナリコピーの所要時間がAV隔離の時間窓を広げる — コピー順序が重要
- 重要ファイル（Tcl/Tkデータ、テーマJSON）は最優先でコピーすべき
- Phase間の時間経過でAV隔離が進行するため、各Phaseがruntime_cacheフォールバックを持つ必要がある

### 5.10 rc13の結果: _tkinter DLL依存の解決失敗

**rc13の結果:**
- `data_cached=3`（tcl_tk_data.zip, blue.json, green.json最優先コピー成功）
- `pyd_cached=76`, `dll_cached=232`, `finder=installed`, `dll_dir_patched=YES`
- `init_tcl_exists=True`, `TCL_LIBRARY`/`TK_LIBRARY`設定済み
- しかし`ImportError: DLL load failed while importing _tkinter: 指定されたモジュールが見つかりません。`

**原因:**
- `_tkinter.pyd`はCエクステンションとして`pyd_cache/`にキャッシュされ、`_SafePydFinder`で正常にロードされた
- しかし`_tkinter.pyd`が依存する`tcl86t.dll`、`tk86t.dll`等のDLLが`_MEI*`のトップレベルにある
- Phase 0.5のos.walkループには`_rel_dir != '.'`制限があり、**トップレベルDLLはコピー対象外**だった
- AV隔離で`_MEI*`のトップレベルDLLが消失 → `_tkinter.pyd`のDLLロードが失敗

**教訓:**
- `.pyd`のimport解決とDLL依存解決は別レイヤー。`.pyd`がキャッシュから読めてもDLL依存が解決できなければ失敗する
- トップレベルDLLは「サイズが大きく隔離リスクが低い」という仮定は誤りだった
- AV隔離は選択的ではなく、`_MEI*`ディレクトリ全体に及ぶ

### 5.11 rc14: 全DLLキャッシュ + DLL検索パス登録

**修正内容:**
- **Phase 0.5のDLL制限撤廃**: `_rel_dir != '.'`条件を削除し、トップレベルDLL（`tcl86t.dll`, `tk86t.dll`, `python312.dll`等）もキャッシュ対象に
- **pyd_cache_rootをDLL検索パスに登録**: `os.add_dll_directory(_pyd_cache_root)`で`pyd_cache/`をWindowsのDLL検索パスに追加。`_tkinter.pyd`の依存DLLが同ディレクトリから解決可能に
- **サイズベースのスキップ最適化**: `os.path.getsize()`で既存キャッシュとサイズ比較。同一なら再コピーをスキップし、2回目以降の起動を大幅高速化
- **診断追加**: `copy_skipped`カウンタと`pyd_cache_dll_dir`ステータスを診断出力に追加

**技術詳細:**
- トップレベルDLLは数十MB（python312.dll: ~6MB, tcl86t.dll: ~2MB等）のため初回起動のコピー時間が増加する
- しかしサイズチェックにより2回目以降はほぼ全ファイルがスキップされるため、初回のみのコスト
- `os.add_dll_directory(_pyd_cache_root)`はPhase 0.5cの`os.add_dll_directory`パッチ**前**に実行されるため、オリジナルAPIで登録

**期待される動作:**
```
初回起動（AV隔離あり）:
  Phase 0.5: 全pyd+全dll（トップレベル含む）→ pyd_cache/にコピー
  pyd_cache_root → os.add_dll_directory()で登録
  Phase 0.5b: _SafePydFinder → _tkinter.pydをpyd_cache/からロード
  _tkinter.pyd → tcl86t.dll/tk86t.dllをpyd_cache/から解決 → 成功

2回目以降:
  Phase 0.5: サイズチェックで大部分スキップ（copy_skipped=300+）
  以下同様 → 高速起動
```

### 5.12 rc14の結果: init.tcl AV隔離

**rc14の結果:**
- `pyd_cache_dll_dir=YES` → `_tkinter`のDLLロード問題は**解決**
- `dll_cached=307`（トップレベルDLL含む全DLL）、`copy_skipped=313`（2回目キャッシュ活用）
- `init_tcl_exists=True`（rthook完了時点ではinit.tclが存在）
- しかしアプリ起動時（line 241）に`_tkinter.TclError: Can't find a usable init.tcl`

**原因:**
- Phase 2が`tcl_tk_data.zip`を`_MEI*`に展開し、`TCL_LIBRARY`も`_MEI*/_tcl_data`を指していた
- rthook完了後〜アプリのCTk初期化までの間にAVが`_MEI*/_tcl_data/init.tcl`を隔離
- `tcl_diag`でも`found_init_tcl=`（空）を確認
- rthook時点の`init_tcl_exists=True`はrthook完了時の一瞬のスナップショットに過ぎない

**教訓:**
- `_MEI*`に展開したファイルはいつでもAVに隔離される可能性がある
- `TCL_LIBRARY`のような環境変数パスも`runtime_cache`を指すべき
- 全てのPhaseで一貫して「`_MEI*`は信頼できない」前提で設計すべき

### 5.13 rc15: Tcl/Tkデータのruntime_cache展開

**修正内容:**
- **Phase 2拡張**: `tcl_tk_data.zip`を`_MEI*`に加えて`runtime_cache`にも展開
- **TCL_LIBRARY/TK_LIBRARY変更**: `runtime_cache/_tcl_data`/`runtime_cache/_tk_data`を優先参照。存在しない場合のみ`_MEI*`にフォールバック

**期待される動作:**
```
Phase 2: tcl_tk_data.zip → _MEI*（互換性）+ runtime_cache（安全コピー）
TCL_LIBRARY → runtime_cache/_tcl_data（AV隔離耐性あり）
init.tcl → runtime_cacheから読み込み → 成功
```

### 5.14 rc15の結果: pyi_rth__tkinter.pyクラッシュ

**rc15の結果:**
- `TCL_LIBRARY=runtime_cache/_tcl_data`（正しく設定されたが...）
- `init_tcl_exists=True`（rthook完了時点では存在）
- `pyi_rth__tkinter.py`（PyInstaller組み込みランタイムフック）が`_MEI/_tcl_data`の存在チェックでFileNotFoundError

**原因:**
- PyInstallerの組み込み`pyi_rth__tkinter.py`は我々のカスタムrthookの**後**に実行される
- このフックは`os.path.isdir(_MEI/_tcl_data)`をチェックし、なければFileNotFoundErrorを発生
- AV隔離で`_MEI/_tcl_data`が消失 → クラッシュ
- さらに、仮にチェックを通過しても`os.environ['TCL_LIBRARY'] = _MEI_path`で我々のruntime_cacheパスを上書きする

**教訓:**
- PyInstallerの組み込みランタイムフックが我々のカスタムフックと競合する
- `hooks/hook-_tkinter.py`（分析フック）のオーバーライドはランタイムフックに影響しない
- ランタイムフックの実行順序: カスタム(`runtime_hooks`) → 組み込み(`rthooks.dat`)

### 5.15 rc16: pyi_rth__tkinter.py無害化

**修正内容:**
- **Phase 2.1**: `pyi_rth__tkinter.py`の2つの問題を同時に解決
  - `os.path.isdir`パッチ: `_MEI/_tcl_data`と`_MEI/_tk_data`に対し常にTrueを返す（AV隔離後もクラッシュしない）
  - `os.environ.__setitem__`パッチ: TCL_LIBRARY/TK_LIBRARYへの書き込みをブロック（runtime_cacheパスの保護）

**技術詳細:**
- `os.path.isdir`パッチ: `_fake_tcl_dirs`(frozenset)にマッチするパスのみTrue返却、他は元関数に委譲
- `os.environ.__class__.__setitem__`パッチ: `_protected_env_keys`にマッチするキーのみ書き込みブロック、他は元関数に委譲
- 両パッチとも極めて限定的なスコープ（各2つのパス/キーのみ）

**期待される動作:**
```
Phase 2: tcl_tk_data.zip → runtime_cache + _MEI に展開
Phase 2.1: os.path.isdir + os.environ パッチ適用
pyi_rth__tkinter.py:
  os.path.isdir(_MEI/_tcl_data) → True（パッチ）
  os.environ['TCL_LIBRARY'] = _MEI_path → ブロック（パッチ）
main.py:
  TCL_LIBRARY → runtime_cache/_tcl_data（保護済み）
  init.tcl → runtime_cacheから読み込み → 成功
```

## 6. 推奨方針

### 短期: Approach B（rc6で完成）

ハイブリッドimport + collections.abc明示バインディング + 常時パス差し替え + __path__書き換え + 最終キャッシュ掃除。
通常時・AV隔離時ともに`runtime_cache/base_library.zip`を参照する。

### 中長期: Approach C（onedirまたはMSIX）

根本原因を排除し、rthookの複雑さを大幅削減。

## 7. 参考URL

### PyInstaller AV関連
- [Issue #8164 - False positives above v5.13.2](https://github.com/pyinstaller/pyinstaller/issues/8164)
- [Issue #6754 - onefile AV false positive](https://github.com/pyinstaller/pyinstaller/issues/6754)
- [Discussion #5877 - AV says exe is a threat](https://github.com/orgs/pyinstaller/discussions/5877)

### PyInstaller runtime hook関連
- [Issue #8909 - pathlib moved out of base_library.zip](https://github.com/pyinstaller/pyinstaller/issues/8909)
- [Issue #3397 - Missing warnings in base_library.zip](https://github.com/pyinstaller/pyinstaller/issues/3397)
- [Issue #1444 - zipimport can't open base_library.zip](https://github.com/pyinstaller/pyinstaller/issues/1444)

### CPython import関連
- [Bug #45776 - abc submodule not attribute of collections](https://bugs.python.org/issue45776)
- [Bug #20784 - collections.abc not defined](https://bugs.python.org/issue20784)
- [CPython typing.py (v3.12)](https://github.com/python/cpython/blob/v3.12.0/Lib/typing.py)

### AV回避手段
- [MSIX packaging for Python](https://82phil.github.io/python/2025/04/24/msix_pyinstaller.html)
- [Py2MSIX](https://github.com/MLT-solutions/Py2MSIX)
- [SignPath.io (OSS無料署名)](https://signpath.io)
- [No more _MEI folder (bootloader customization)](https://offensivepython.com/index.php/2025/02/27/no-more-mei-folder-with-pyinstaller/)
