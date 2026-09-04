"""
一覧まわりの共通部品（list_ui.py）に関するテスト。

背景:
  3タブとも「一覧から選んで対象に加え、編集し、いらなくなったら消す」という同じ形で、
  以下がそれぞれのファイルに別々に書かれていた:
    - 「編集済みのみ表示」「未編集のみ表示」の排他制御（3ファイルに同一コード）
    - 検索語＋編集済みフィルタの判定
    - 「●」の編集済みマーク
    - 削除の確認ダイアログ（共通の注意文＋Undoの案内）
    - 直近1回分だけ戻せるUndo（記録・ボタンの有効/無効・破棄）

  list_ui.py に集約し、3タブが同じ部品を使うようにした。
"""

import unittest

from helpers import make_window, get_app  # noqa: F401
import list_ui
from PyQt6.QtWidgets import QPushButton


class TestMarked(unittest.TestCase):
    def test_edited_gets_a_dot(self):
        self.assertTrue(list_ui.marked(True, "x.png").startswith("●"))

    def test_unedited_is_indented_to_match(self):
        edited = list_ui.marked(True, "x.png")
        plain = list_ui.marked(False, "x.png")
        self.assertNotIn("●", plain)
        self.assertEqual(len(edited), len(plain), "字下げ幅が揃っていない")


class TestMatchesFilter(unittest.TestCase):
    def test_no_query_and_no_filter_shows_everything(self):
        self.assertTrue(list_ui.matches_filter("", False, False, False, "diamond_ore.png"))
        self.assertTrue(list_ui.matches_filter("", True, False, False, "diamond_ore.png"))

    def test_query_matches_any_of_the_texts(self):
        self.assertTrue(list_ui.matches_filter("ダイヤ", False, False, False, "diamond_ore.png", "ダイヤ鉱石"))
        self.assertTrue(list_ui.matches_filter("diamond", False, False, False, "diamond_ore.png", "ダイヤ鉱石"))
        self.assertFalse(list_ui.matches_filter("金", False, False, False, "diamond_ore.png", "ダイヤ鉱石"))

    def test_query_is_case_insensitive(self):
        self.assertTrue(list_ui.matches_filter("DIAMOND", False, False, False, "diamond_ore.png"))

    def test_edited_only(self):
        self.assertTrue(list_ui.matches_filter("", True, True, False, "a"))
        self.assertFalse(list_ui.matches_filter("", False, True, False, "a"))

    def test_unedited_only(self):
        self.assertTrue(list_ui.matches_filter("", False, False, True, "a"))
        self.assertFalse(list_ui.matches_filter("", True, False, True, "a"))


class TestEditedFilterBox(unittest.TestCase):
    def setUp(self):
        get_app()
        self.box = list_ui.EditedFilterBox()

    def test_checking_one_unchecks_the_other(self):
        self.box.edited_only_checkbox.setChecked(True)
        self.box.unedited_only_checkbox.setChecked(True)
        self.assertFalse(self.box.edited_only_checkbox.isChecked(),
                         "両方ONは矛盾するので、片方は自動でOFFになるはず")
        self.assertTrue(self.box.unedited_only_checkbox.isChecked())

    def test_changed_is_emitted_once_per_toggle(self):
        counter = []
        self.box.changed.connect(lambda: counter.append(1))
        self.box.edited_only_checkbox.setChecked(True)
        self.assertEqual(len(counter), 1, "排他制御の巻き添えで余分にシグナルが出ている")

    def test_is_filtering(self):
        self.assertFalse(self.box.is_filtering())
        self.box.edited_only_checkbox.setChecked(True)
        self.assertTrue(self.box.is_filtering())


class TestUndoSlot(unittest.TestCase):
    def setUp(self):
        get_app()
        self.button = QPushButton()
        self.slot = list_ui.UndoSlot(self.button)

    def test_button_starts_disabled(self):
        self.assertFalse(self.button.isEnabled())

    def test_store_enables_and_take_disables(self):
        self.slot.store([1, 2, 3])
        self.assertTrue(self.button.isEnabled())
        self.assertEqual(self.slot.take(), [1, 2, 3])
        self.assertFalse(self.button.isEnabled())

    def test_take_only_works_once(self):
        self.slot.store(["x"])
        self.slot.take()
        self.assertIsNone(self.slot.take(), "1回分しか戻せない仕様のはず")

    def test_works_without_a_button(self):
        slot = list_ui.UndoSlot()
        slot.store("payload")
        self.assertTrue(slot.has_payload())
        self.assertEqual(slot.take(), "payload")


class TestAllThreeTabsUseTheSharedParts(unittest.TestCase):
    def setUp(self):
        self.window = make_window()

    def test_every_tab_has_a_shared_filter_box(self):
        self.assertIsInstance(self.window.block_tab.browse_filter, list_ui.EditedFilterBox)
        self.assertIsInstance(self.window.item_tab.browse_filter, list_ui.EditedFilterBox)
        self.assertIsInstance(self.window.gui_icon_tab.variant_filter, list_ui.EditedFilterBox)

    def test_every_tab_has_a_shared_undo_slot(self):
        self.assertIsInstance(self.window.block_tab.undo_remove_blocks, list_ui.UndoSlot)
        self.assertIsInstance(self.window.item_tab.undo_remove_targets, list_ui.UndoSlot)
        self.assertIsInstance(self.window.gui_icon_tab.undo_remove_variants, list_ui.UndoSlot)

    def test_old_checkbox_attributes_still_point_at_the_shared_widgets(self):
        """既存コード・テストが触っているチェックボックス名も、共通部品の中身を指すこと。"""
        bt = self.window.block_tab
        self.assertIs(bt.block_edited_only_checkbox, bt.browse_filter.edited_only_checkbox)
        it = self.window.item_tab
        self.assertIs(it.edited_only_checkbox, it.browse_filter.edited_only_checkbox)
        gt = self.window.gui_icon_tab
        self.assertIs(gt.edited_only_checkbox, gt.variant_filter.edited_only_checkbox)

    def test_gui_icon_filter_still_matches_japanese_labels(self):
        """状態名の絞り込みは、日本語表示名でも英語ファイル名でも引けること。"""
        gt = self.window.gui_icon_tab
        gt.variant_search_box.setText("満タン")
        self.assertGreater(gt.variant_list.count(), 0)
        gt.variant_search_box.setText("full")
        self.assertGreater(gt.variant_list.count(), 0)
        gt.variant_search_box.setText("存在しない状態名")
        self.assertEqual(gt.variant_list.count(), 0)


if __name__ == "__main__":
    unittest.main()
