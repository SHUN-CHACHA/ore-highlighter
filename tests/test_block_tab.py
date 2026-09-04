"""
ブロックエフェクトタブの基本操作テスト。
（テクスチャ読み込み・対象への追加・エフェクト編集・削除と取り消し・フィルタ）
"""

import os
import unittest

from helpers import (  # noqa: F401
    make_window, make_texture_folder, make_jar, make_ready_window, silence_dialogs,
)
import effect_catalog as EC


class TestBlockTabBasics(unittest.TestCase):
    def setUp(self):
        silence_dialogs()
        self.window = make_window()
        self.bt = self.window.block_tab
        self.tmp, self.block_dir, self.item_dir = make_texture_folder()

    def test_load_folder_populates_browse_list(self):
        self.bt.load_textures_folder(self.block_dir)
        self.assertEqual(self.bt.browse_list.count(), 3)

    def test_load_folder_wires_item_dir(self):
        """textures/block の兄弟フォルダ textures/item がアイテムタブへ渡ること。"""
        self.bt.load_textures_folder(self.block_dir)
        self.assertEqual(self.window.item_tab.items_dir, self.item_dir)

    def test_load_jar_extracts_block_hud_and_item(self):
        jar = make_jar(self.tmp)
        self.bt.load_jar(jar)
        self.assertEqual(self.bt.browse_list.count(), 2)
        self.assertTrue(os.path.isdir(self.window.gui_icon_tab.reference_dir or ""))
        self.assertTrue(os.path.isdir(self.window.item_tab.items_dir or ""))

    def test_search_filters_browse_list(self):
        self.bt.load_textures_folder(self.block_dir)
        self.bt.search_box.setText("diamond")
        self.assertEqual(self.bt.browse_list.count(), 1)
        self.bt.search_box.setText("")
        self.assertEqual(self.bt.browse_list.count(), 3)

    def test_edited_and_unedited_filters_are_exclusive(self):
        """「編集済みのみ」と「未編集のみ」は同時にONにできない。"""
        self.bt.load_textures_folder(self.block_dir)
        self.bt.browse_list.selectAll()
        self.bt.on_add_to_targets()

        self.bt.block_edited_only_checkbox.setChecked(True)
        self.assertEqual(self.bt.browse_list.count(), 3)

        self.bt.block_unedited_only_checkbox.setChecked(True)
        self.assertFalse(self.bt.block_edited_only_checkbox.isChecked())
        self.assertEqual(self.bt.browse_list.count(), 0)

    def test_add_to_targets_skips_duplicates(self):
        self.bt.load_textures_folder(self.block_dir)
        self.bt.browse_list.selectAll()
        self.bt.on_add_to_targets()
        self.bt.browse_list.selectAll()
        self.bt.on_add_to_targets()
        self.assertEqual(len(self.bt.target_blocks), 3)


class TestBlockTabEditing(unittest.TestCase):
    def setUp(self):
        silence_dialogs()
        self.window, self.bt, self.tmp, self.block_dir, self.out = make_ready_window()

    def test_editing_effect_updates_selected_block(self):
        self.bt.target_list.setCurrentRow(0)
        self.bt.effect_combo.setCurrentText("点滅")
        self.bt.dark_factor_spin.setValue(0.5)
        self.assertEqual(self.bt.target_blocks[0]["effect"], EC.BLINK)
        self.assertEqual(self.bt.target_blocks[0]["dark_factor"], 0.5)

    def test_multi_select_applies_effect_to_all(self):
        self.bt.target_list.selectAll()
        self.bt.effect_combo.setCurrentText("枠線")
        for block in self.bt.target_blocks:
            self.assertEqual(block["effect"], EC.OUTLINE)

    def test_remove_and_undo_restores_position(self):
        """削除を元に戻したとき、元の並び順に戻ること（1回分のみ）。"""
        original = [b["filename"] for b in self.bt.target_blocks]

        self.bt.target_list.setCurrentRow(1)
        self.bt.on_remove_targets()
        self.assertEqual(len(self.bt.target_blocks), 2)
        self.assertTrue(self.bt.undo_remove_blocks_btn.isEnabled())

        self.bt.on_undo_remove_blocks()
        self.assertEqual([b["filename"] for b in self.bt.target_blocks], original)
        self.assertFalse(
            self.bt.undo_remove_blocks_btn.isEnabled(),
            "取り消しは1回分のみ。実行後はボタンが無効になるはず",
        )

    def test_preview_creates_gif(self):
        self.bt.target_list.setCurrentRow(0)
        self.bt.on_preview()
        self.assertTrue(os.path.exists(self.bt._preview_gif_path))
        self.assertGreater(os.path.getsize(self.bt._preview_gif_path), 0)

    def test_param_visibility_follows_effect(self):
        """エフェクト種類に応じて、関係ないパラメータが無効化されること。"""
        self.bt.target_list.setCurrentRow(0)

        self.bt.effect_combo.setCurrentText("点滅")
        self.assertTrue(self.bt.dark_factor_spin.isEnabled())
        self.assertFalse(self.bt.thickness_spin.isEnabled())

        self.bt.effect_combo.setCurrentText("枠線")
        self.assertTrue(self.bt.thickness_spin.isEnabled())
        self.assertFalse(self.bt.dark_factor_spin.isEnabled())

    def test_editor_disabled_without_selection(self):
        self.bt.target_list.clearSelection()
        self.assertFalse(self.bt.effect_combo.isEnabled())


if __name__ == "__main__":
    unittest.main()
