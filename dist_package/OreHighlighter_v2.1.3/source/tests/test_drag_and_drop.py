"""
ドラッグ&ドロップの振り分けテスト。

D&DはQMainWindowレベルで受け、アクティブなタブと拡張子で振り分ける。
ここは手作業だと検証が面倒（実際にファイルを掴んで落とす必要がある）ため、
本物の QDropEvent を組み立てて自動で確認する。
"""

import os
import tempfile
import unittest

from helpers import (  # noqa: F401
    make_window, make_ready_window, make_texture_folder, make_jar,
    silence_dialogs, drop_on,
)


class TestDragAndDrop(unittest.TestCase):
    def setUp(self):
        silence_dialogs()
        self.window = make_window()
        self.bt = self.window.block_tab
        self.tmp, self.block_dir, self.item_dir = make_texture_folder()

    def test_drop_jar_on_block_tab(self):
        accepted = drop_on(self.window, make_jar(self.tmp), self.bt)
        self.assertTrue(accepted)
        self.assertEqual(self.bt.browse_list.count(), 2)

    def test_drop_folder_on_block_tab(self):
        accepted = drop_on(self.window, self.block_dir, self.bt)
        self.assertTrue(accepted)
        self.assertEqual(self.bt.browse_list.count(), 3)
        self.assertIn("ドラッグ&ドロップ", self.bt.status_label.text())

    def test_drop_project_zip_on_block_tab(self):
        """生成済みパックのzipを落とすと、プロジェクトとして読み込まれること。"""
        window, bt, tmp, block_dir, out = make_ready_window("DropPack")
        window.on_generate()
        zip_path = os.path.join(out, "DropPack.zip")

        other = make_window()
        other.block_tab.load_textures_folder(block_dir)
        accepted = drop_on(other, zip_path, other.block_tab)

        self.assertTrue(accepted)
        self.assertEqual(len(other.block_tab.target_blocks), 3)

    def test_drop_png_on_block_tab_is_ignored(self):
        """
        画像はGUIアイコン／アイテムタブ用。ブロックタブに落としても
        対象ブロックが増えたりしないこと（案内だけ出して何もしない）。
        """
        png = os.path.join(self.block_dir, "diamond_ore.png")
        before = len(self.bt.target_blocks)
        drop_on(self.window, png, self.bt)
        self.assertEqual(len(self.bt.target_blocks), before)

    def test_drop_nonexistent_path_does_nothing(self):
        accepted = drop_on(self.window, os.path.join(self.tmp, "無い.jar"), self.bt)
        self.assertFalse(accepted)

    def test_drop_broken_zip_shows_error_without_crashing(self):
        broken = os.path.join(self.tmp, "broken.zip")
        with open(broken, "wb") as f:
            f.write(b"this is not a zip file")
        drop_on(self.window, broken, self.bt)  # 例外が外に出なければ合格
        self.assertEqual(len(self.bt.target_blocks), 0)

    def test_drop_folder_on_gui_icon_tab_goes_to_pack_import(self):
        """
        同じフォルダでも、アクティブなタブによって行き先が変わること。
        （GUIアイコン編集タブではパック読み込み扱いになり、
        　ブロックタブの候補一覧は増えない）
        """
        pack_root = tempfile.mkdtemp(prefix="ore_test_pack_")
        hud = os.path.join(pack_root, "assets", "minecraft",
                           "textures", "gui", "sprites", "hud")
        os.makedirs(hud)
        with open(os.path.join(pack_root, "pack.mcmeta"), "w", encoding="utf-8") as f:
            f.write('{"pack": {"description": "test"}}')

        drop_on(self.window, pack_root, self.window.gui_icon_tab)
        self.assertEqual(self.bt.browse_list.count(), 0)


if __name__ == "__main__":
    unittest.main()
