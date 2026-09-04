"""
「読み込み」タブ（SourceImportTab）への集約に関するテスト。

背景:
  読み込みの入口が3つのタブに散らばっていた（ブロックエフェクトタブの
  ランチャー検出/jar/フォルダ/既存プロジェクト、GUIアイコン編集タブの
  参照元フォルダ/既存パック読み込み）。ユーザーから「同じ機能は統一して
  1つのタブにまとめたい」という要望があり、「読み込み」タブに集約した。

設計上の約束（source_tab.py 参照）:
  - SourceImportTab はロジックも状態も持たない「並べ直すだけの器」
  - ボタン等の実体は BlockEffectTab / GuiIconEditorTab が build_source_widgets()
    で作り、シグナル接続も各タブ側で完結している
  - よって既存の読み込みロジック（on_open_folder / _load_jar_path など）は
    self.folder_label / self.launcher_jar_list をそのまま参照でき、無変更で動く

このテストは「確かに新タブ配下に移動したこと」「旧タブに残っていないこと」
「移動後も既存ロジックが動くこと」の3点を確認する。
"""

import os
import unittest

from helpers import (
    make_window, make_ready_window, make_texture_folder, make_jar,
    drop_on, silence_dialogs,
)
from PyQt6.QtWidgets import QScrollArea, QPushButton, QListWidget, QLabel


class TestSourceTabRegistered(unittest.TestCase):
    def setUp(self):
        self.window = make_window()

    def test_source_tab_is_registered_first(self):
        labels = [self.window.tabs.tabText(i) for i in range(self.window.tabs.count())]
        self.assertIn("読み込み", labels)
        # 作業の起点なので先頭に置く
        self.assertEqual(labels[0], "読み込み")

    def test_source_tab_is_wrapped_in_scroll_area(self):
        """QTabWidget.minimumSizeHint() は全タブ中の最大値で決まるため、
        内容量の多い新タブは必ずQScrollAreaで包む（引き継ぎ資料 3.6節）。"""
        self.assertTrue(self.window.source_tab.findChildren(QScrollArea))


class TestWidgetsMovedToSourceTab(unittest.TestCase):
    def setUp(self):
        self.window = make_window()
        self.source = self.window.source_tab
        self.bt = self.window.block_tab
        self.gt = self.window.gui_icon_tab

    def _descendants(self, cls):
        return self.source.findChildren(cls)

    def test_block_source_widgets_are_under_source_tab(self):
        buttons = self._descendants(QPushButton)
        for name in ("official_scan_btn", "prism_scan_btn", "launcher_scan_btn",
                     "open_folder_btn", "open_jar_btn",
                     "project_folder_btn", "project_zip_btn",
                     "project_open_backup_btn"):
            self.assertIn(getattr(self.bt, name), buttons, f"{name} が読み込みタブ配下に無い")
        self.assertIn(self.bt.folder_label, self._descendants(QLabel))
        self.assertIn(self.bt.launcher_jar_list, self._descendants(QListWidget))

    def test_gui_icon_source_widgets_are_under_source_tab(self):
        buttons = self._descendants(QPushButton)
        for name in ("ref_dir_btn", "import_pack_folder_btn",
                     "import_pack_zip_btn", "open_backup_folder_btn"):
            self.assertIn(getattr(self.gt, name), buttons, f"{name} が読み込みタブ配下に無い")

    def test_widgets_no_longer_remain_in_old_tabs(self):
        """移動漏れで旧タブにも残っていないこと（二重表示の防止）。"""
        block_buttons = self.bt.findChildren(QPushButton)
        for name in ("official_scan_btn", "open_jar_btn", "project_folder_btn"):
            self.assertNotIn(
                getattr(self.bt, name), block_buttons,
                f"{name} がまだブロックエフェクトタブ側に残っている",
            )
        self.assertNotIn(self.bt.folder_label, self.bt.findChildren(QLabel))

        gui_buttons = self.gt.findChildren(QPushButton)
        for name in ("ref_dir_btn", "import_pack_folder_btn"):
            self.assertNotIn(
                getattr(self.gt, name), gui_buttons,
                f"{name} がまだGUIアイコン編集タブ側に残っている",
            )


class TestSourceTabStillFunctional(unittest.TestCase):
    """移動後も、既存の読み込みロジックが変更なしで動くこと。"""

    def setUp(self):
        self.window = make_window()
        self.bt = self.window.block_tab

    def test_load_textures_folder_updates_relocated_label(self):
        _tmp, block_dir, _item = make_texture_folder()
        self.bt.load_textures_folder(block_dir)
        self.assertIn(block_dir, self.bt.folder_label.text())
        self.assertGreater(self.bt.browse_list.count(), 0)

    def test_load_jar_updates_relocated_label(self):
        tmp, _block_dir, _item = make_texture_folder()
        jar = make_jar(tmp)
        silence_dialogs()
        self.bt.load_jar(jar)
        self.assertIn(jar, self.bt.folder_label.text())
        self.assertGreater(self.bt.browse_list.count(), 0)

    def test_status_is_mirrored_to_source_tab(self):
        """読み込み系の結果は、操作したタブ（＝読み込みタブ）にも表示されること。"""
        self.bt._set_status("テスト用メッセージ")
        self.assertEqual(self.window.source_tab.status_label.text(), "テスト用メッセージ")

    def test_gui_icon_import_status_is_mirrored_to_source_tab(self):
        self.window.gui_icon_tab._set_import_status("アイコン読み込みメッセージ")
        self.assertEqual(
            self.window.source_tab.status_label.text(), "アイコン読み込みメッセージ"
        )


class TestDragAndDropOnSourceTab(unittest.TestCase):
    """読み込みタブは読み込みの入口なので、D&Dもここで受けられること。"""

    def test_folder_drop_on_source_tab_loads_textures(self):
        window = make_window()
        _tmp, block_dir, _item = make_texture_folder()
        accepted = drop_on(window, block_dir, window.source_tab)
        self.assertTrue(accepted)
        self.assertEqual(window.block_tab.textures_dir, block_dir)

    def test_jar_drop_on_source_tab_loads_jar(self):
        window = make_window()
        tmp, _block_dir, _item = make_texture_folder()
        jar = make_jar(tmp)
        silence_dialogs()
        accepted = drop_on(window, jar, window.source_tab)
        self.assertTrue(accepted)
        self.assertGreater(window.block_tab.browse_list.count(), 0)

    def test_zip_drop_on_source_tab_is_treated_as_project_import(self):
        """読み込みタブは「既存プロジェクトを開く」導線を持つので、
        zipのドロップはブロックエフェクトタブと同じ扱いになること。"""
        window, _bt, _tmp, block_dir, out = make_ready_window("SourceTabDropPack")
        window.on_generate()
        zip_path = os.path.join(out, "SourceTabDropPack.zip")
        self.assertTrue(os.path.exists(zip_path), "生成物が見つからない")

        fresh = make_window()
        fresh.block_tab.load_textures_folder(block_dir)
        accepted = drop_on(fresh, zip_path, fresh.source_tab)

        self.assertTrue(accepted)
        self.assertEqual(len(fresh.block_tab.target_blocks), 3,
                         "読み込みタブへのzipドロップでプロジェクトが復元されていない")


if __name__ == "__main__":
    unittest.main()
