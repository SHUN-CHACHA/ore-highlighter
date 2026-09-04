"""
テストをまとめて実行するスクリプト。

使い方（ソースルートでも tests/ の中でも可）:
    python tests/run_tests.py

標準のunittestだけで動くので、pytest等の追加インストールは不要。
PyQt6 と Pillow が入っていれば動く。

Copyright (c) 2026 旬茶
Licensed under the MIT License.
"""

import os
import sys
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if TESTS_DIR not in sys.path:
    sys.path.insert(0, TESTS_DIR)


def main():
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=TESTS_DIR, pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print()
    if result.wasSuccessful():
        print(f"=== 全テスト成功（{result.testsRun}件） ===")
    else:
        print(
            f"=== 失敗 {len(result.failures)}件 / エラー {len(result.errors)}件 "
            f"（実行 {result.testsRun}件） ==="
        )
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
