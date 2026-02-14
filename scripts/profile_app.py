#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kototsuna パフォーマンスプロファイリングスクリプト

使用方法:
    python scripts/profile_app.py cpu     # cProfileでCPUプロファイリング
    python scripts/profile_app.py memory  # メモリプロファイリングの案内
"""
import sys
import os

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


def run_cpu_profile():
    """cProfileでアプリケーションのCPUプロファイリングを実行"""
    import cProfile
    import pstats
    from io import StringIO

    output_file = os.path.join(PROJECT_ROOT, "profile_output.prof")

    print("=== CPU プロファイリング ===")
    print(f"出力ファイル: {output_file}")
    print("アプリケーションを起動します。終了後にプロファイル結果を表示します。")
    print("-" * 60)

    profiler = cProfile.Profile()
    profiler.enable()

    try:
        from main import main
        main()
    except SystemExit:
        pass
    except KeyboardInterrupt:
        print("\n中断されました。")
    finally:
        profiler.disable()

        # ファイルに保存
        profiler.dump_stats(output_file)

        # コンソールに上位30関数を表示
        stream = StringIO()
        stats = pstats.Stats(profiler, stream=stream)
        stats.sort_stats("cumulative")
        stats.print_stats(30)
        print(stream.getvalue())

        print(f"\n詳細な結果: {output_file}")
        print("可視化ツール: snakeviz")
        print(f"  pip install snakeviz && snakeviz {output_file}")


def show_memory_guide():
    """メモリプロファイリングの案内を表示"""
    print("=== メモリプロファイリング ===")
    print()
    print("方法1: memory_profiler (行単位)")
    print("  pip install memory_profiler")
    print("  python -m memory_profiler main.py")
    print()
    print("方法2: tracemalloc (Python標準)")
    print("  import tracemalloc")
    print("  tracemalloc.start()")
    print("  # ... アプリケーション実行 ...")
    print("  snapshot = tracemalloc.take_snapshot()")
    print("  top_stats = snapshot.statistics('lineno')")
    print()
    print("方法3: objgraph (オブジェクト参照)")
    print("  pip install objgraph")
    print("  import objgraph")
    print("  objgraph.show_most_common_types(limit=20)")
    print()
    print("方法4: リソースモニター内蔵")
    print("  アプリの「リソース」パネルでリアルタイムのメモリ使用量を確認できます。")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    mode = sys.argv[1].lower()

    if mode == "cpu":
        run_cpu_profile()
    elif mode == "memory":
        show_memory_guide()
    else:
        print(f"不明なモード: {mode}")
        print("使用可能: cpu, memory")
        sys.exit(1)


if __name__ == "__main__":
    main()
