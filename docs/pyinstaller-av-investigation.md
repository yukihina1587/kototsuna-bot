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
| v1.3.1-rc9 | `.pyd`をruntime_cacheにプリキャッシュ + meta_path finderで迂回 | テスト中 |

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

**教訓:**
- `collect_all()`はPythonモジュールを網羅的に収集するが、Cエクステンション（.pyd/.so）は漏れることがある
- `hiddenimports`はPythonモジュールのimportグラフに基づくため、ネイティブ拡張には効かない場合がある
- 確実な方法は`binaries`リストに`.pyd`ファイルパスを直接追加すること
- **バンドルだけでは不十分**: `.pyd`がバンドルに含まれていても、AV隔離で実行時に消失する
- base_library.zipで確立した「runtime_cacheプリキャッシュ + import迂回」パターンはCエクステンションにも適用可能

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
