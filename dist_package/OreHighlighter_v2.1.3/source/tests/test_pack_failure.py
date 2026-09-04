"""
リソースパック生成の失敗時の挙動テスト（v1.2.4 で修正した不具合の回帰テスト）。

守りたいこと:
  1. 失敗したら、作りかけのフォルダを出力先に残さない
     （残すとMinecraftが「ブロックだけ適用されアイテムが欠けたパック」として読んでしまう）
  2. 失敗しても、前回生成したzipを壊さない
"""

import os
import unittest
import zipfile

from helpers import (  # noqa: F401
    make_ready_window, silence_dialogs, raiser,
)
import block_tab as BT


class TestGenerationFailure(unittest.TestCase):
    def setUp(self):
        self.criticals = silence_dialogs()
        self.window, self.bt, self.tmp, self.block_dir, self.out = make_ready_window("P")

    def _break_item_export(self):
        self.window.item_tab.export_all = raiser("アイテム書き出しで想定外のエラー")

    def test_failure_leaves_output_dir_clean(self):
        self._break_item_export()
        self.window.on_generate()

        self.assertEqual(os.listdir(self.out), [], "作りかけのファイルが残っている")
        self.assertTrue(self.criticals, "エラーダイアログが出ていない")
        self.assertIn("作りかけのファイルは出力先に残していません", self.criticals[0])
        self.assertNotIn("前回生成した", self.criticals[0])

    def test_failure_keeps_previous_zip_intact(self):
        """一度成功した後に失敗しても、前回のパックが無傷で残ること。"""
        self.window.on_generate()
        zip_path = os.path.join(self.out, "P.zip")
        before = open(zip_path, "rb").read()

        self._break_item_export()
        self.criticals.clear()
        self.window.on_generate()

        self.assertEqual(os.listdir(self.out), ["P.zip"])
        self.assertEqual(open(zip_path, "rb").read(), before, "前回のzipが書き換わっている")
        with zipfile.ZipFile(zip_path) as z:
            self.assertIsNone(z.testzip(), "前回のzipが壊れた")
        self.assertIn("前回生成した「P.zip」はそのまま残っています", self.criticals[0])

    def test_zip_write_failure_leaves_no_tmp_file(self):
        """
        zip書き込み中の失敗（ディスク不足・Minecraftによるファイルロックなど）でも、
        一時ファイル(.zip.tmp)を残さず、前回のzipも壊さないこと。
        """
        self.window.on_generate()
        zip_path = os.path.join(self.out, "P.zip")
        before = open(zip_path, "rb").read()

        original = zipfile.ZipFile

        class ExplodingZipFile(zipfile.ZipFile):
            def write(self, *args, **kwargs):
                raise OSError("ディスクの空き容量がありません")

        BT.zipfile.ZipFile = ExplodingZipFile
        try:
            self.window.on_generate()
        finally:
            BT.zipfile.ZipFile = original

        self.assertEqual(os.listdir(self.out), ["P.zip"], "一時ファイルが残っている")
        self.assertEqual(open(zip_path, "rb").read(), before, "前回のzipが壊れた")

    def test_normal_generation_still_works(self):
        """失敗時の後始末を入れたことで、正常系が壊れていないことの確認。"""
        self.window.on_generate()
        self.assertEqual(os.listdir(self.out), ["P.zip"])
        with zipfile.ZipFile(os.path.join(self.out, "P.zip")) as z:
            self.assertIsNone(z.testzip())
            self.assertIn("pack.mcmeta", z.namelist())
        self.assertFalse(self.criticals, f"エラーが出ている: {self.criticals}")


if __name__ == "__main__":
    unittest.main()
