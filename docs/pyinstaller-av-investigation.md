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

### RC期（v1.3.1-rc1〜rc3）

| Ver | 修正内容 | 結果 |
|-----|---------|------|
| v1.3.1-rc1 | エラーログexe隣出力・TOCTOU修正 | `collections.abc.Hashable`消失 |
| v1.3.1-rc2 | _MEI正常時パス差し替えスキップ | 同上（_SafeBaseLibFinder残存） |
| v1.3.1-rc3 | _SafeBaseLibFinderもスキップ | 同上（deferred importが根本原因） |

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

## 5. 推奨方針

### 短期（rc4）: Approach B

ハイブリッドimport戦略を実装。通常時はv1.3.0互換、AV隔離時のみフォールバックし、
Phase 0後に`collections.abc`の親属性バインディングを明示的に確立する。

### 中長期: Approach C（onedirまたはMSIX）

根本原因を排除し、rthookの複雑さを大幅削減。

## 6. 参考URL

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
