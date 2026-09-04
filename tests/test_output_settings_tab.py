"""
「出力設定」タブの分離に関するテスト。

背景:
  パック名・説明文・パックアイコン・出力先・Prism Launcher検出は、
  以前はブロックエフェクトタブの右側パネル（エフェクト設定・プレビューと
  同じ場所）に同居していたが、見つけにくいという要望を受けて独立した
  「出力設定」タブに分離した。

  ウィジェット自体（self.pack_name_edit 等）は引き続き BlockEffectTab の
  インスタンス属性として存在し、on_generate() 等の既存ロジックは
  変更なしで動作し続ける必要がある。このテストはその両方を確認する。
"""

import unittest

from helpers import make_window, make_ready_window, silence_dialogs
from PyQt6.QtWidgets import QScrollArea, QLineEdit, QComboBox


class TestOutputSettingsTabExists(unittest.TestCase):
    def setUp(self):
        self.window = make_window()

    def test_output_settings_tab_is_registered(self):
        labels = [self.window.tabs.tabText(i) for i in range(self.window.tabs.count())]
        self.assertIn("出力設定", labels)

    def test_output_settings_tab_is_second(self):
        """「読み込み → 出力設定」と、パックの入口と出口が先頭2つに並ぶこと。"""
        labels = [self.window.tabs.tabText(i) for i in range(self.window.tabs.count())]
        self.assertEqual(labels[:2], ["読み込み", "出力設定"])

    def test_output_settings_tab_is_wrapped_in_scroll_area(self):
        tab = self.window.block_tab.output_settings_tab
        self.assertIsInstance(tab, QScrollArea)

    def test_output_settings_widgets_live_on_block_tab(self):
        bt = self.window.block_tab
        self.assertIsInstance(bt.pack_name_edit, QLineEdit)
        self.assertIsInstance(bt.pack_desc_edit, QLineEdit)
        self.assertIsInstance(bt.output_dir_label, QLineEdit)
        self.assertIsInstance(bt.prism_combo, QComboBox)

    def test_output_settings_widgets_are_descendants_of_the_new_tab(self):
        """パック名欄などが、確かに新タブのツリー配下に存在すること
        （移動漏れで別の場所に残っていないことの確認）。"""
        bt = self.window.block_tab
        tab = bt.output_settings_tab
        descendants = tab.findChildren(QLineEdit)
        self.assertIn(bt.pack_name_edit, descendants)
        self.assertIn(bt.pack_desc_edit, descendants)
        self.assertIn(bt.output_dir_label, descendants)

    def test_block_tab_editor_panel_no_longer_contains_output_widgets(self):
        """エフェクト設定パネル側には、もう出力設定ウィジェットが無いこと。"""
        bt = self.window.block_tab
        # editor_panel はブロックタブ本体（output_settings_tabとは別）側の
        # QScrollArea群のいずれにも pack_name_edit を含んではいけない。
        for sa in bt.findChildren(QScrollArea):
            if sa is bt.output_settings_tab:
                continue
            self.assertNotIn(
                bt.pack_name_edit, sa.findChildren(QLineEdit),
                "パック名欄がまだ旧パネル側に残っている",
            )


class TestOutputSettingsStillFunctional(unittest.TestCase):
    """タブを分離しても、既存のパック生成フローが壊れていないことを確認する。"""

    def test_generate_uses_relocated_widgets(self):
        w, bt, tmp, block_dir, out = make_ready_window(pack_name="MovedTabPack")
        silence_dialogs()
        bt.pack_desc_edit.setText("分離後も動作すること")
        pack_name, output_dir = bt.get_pack_output_info()
        self.assertEqual(pack_name, "MovedTabPack")
        self.assertEqual(output_dir, out)
        self.assertEqual(bt.get_pack_name(), "MovedTabPack")


if __name__ == "__main__":
    unittest.main()
