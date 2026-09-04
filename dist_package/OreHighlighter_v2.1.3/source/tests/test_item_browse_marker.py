"""
アイテムテクスチャ編集タブ「アイテムテクスチャ一覧」（左のブラウズリスト）の
「編集済み」マーク・フィルタに関するテスト。

背景:
  以前は「編集済み」の判定が「対象アイテムに追加済みか」になっていた。
  しかし対象に追加しただけでは何も変わらず（外部PNG画像もエフェクトも未設定の
  状態では export_all() の対象にすらならない）、実際に外部PNG画像やエフェクトを
  設定して初めて「編集済み」と呼ぶべきなので、判定基準を _has_content() に統一した。
  あわせて、左の一覧にも対象アイテム一覧と同じ「●」マークを表示するようにし、
  外部PNG画像を選んだ直後などにその場で反映されることを確認する。

  ついでに、ドット絵エディタで編集した後でも「外部PNG画像を解除（オリジナルに
  戻す）」で本当にオリジナルへ戻せることも確認する（別PCへの配布とは無関係の、
  単なる編集操作の可逆性の話）。
"""

import os
import unittest

from helpers import make_ready_window, silence_dialogs  # noqa: F401
from PIL import Image
from PyQt6.QtCore import Qt


class TestItemBrowseMarker(unittest.TestCase):
    def setUp(self):
        silence_dialogs()
        self.window, self.bt, self.tmp, self.block_dir, self.out = make_ready_window("MarkerTest")
        self.item = self.window.item_tab
        self.fn = sorted(os.listdir(self.item.items_dir))[0]

    def _browse_item_for(self, fn):
        for i in range(self.item.browse_list.count()):
            it = self.item.browse_list.item(i)
            if it.data(Qt.ItemDataRole.UserRole) == fn:
                return it
        return None

    def _add_as_target(self):
        it = self._browse_item_for(self.fn)
        self.item.browse_list.clearSelection()
        it.setSelected(True)
        self.item._on_add_targets()
        # 対象選択（右の編集エリアを開ける状態にする）
        target_it = self.item.target_list.item(0)
        self.item.target_list.setCurrentItem(target_it)
        target_it.setSelected(True)
        self.item._on_target_selected()

    def test_target_without_content_is_not_marked_edited(self):
        """対象に追加しただけ（まだ何も編集していない）では「編集済み」扱いにしない。"""
        self._add_as_target()
        browse_item = self._browse_item_for(self.fn)
        self.assertFalse(browse_item.text().startswith("●"))

        self.item.edited_only_checkbox.setChecked(True)
        self.assertIsNone(self._browse_item_for(self.fn), "まだ未編集なのに「編集済みのみ表示」に出てしまっている")

    def test_choosing_external_image_marks_browse_list_item(self):
        self._add_as_target()
        png_path = os.path.join(self.tmp, "custom.png")
        Image.new("RGBA", (16, 16), (9, 9, 9, 255)).save(png_path)

        self.item.import_image_path(png_path)

        browse_item = self._browse_item_for(self.fn)
        self.assertTrue(browse_item.text().startswith("●"), "外部PNG選択後、一覧に●が付いていない")

        self.item.edited_only_checkbox.setChecked(True)
        self.assertIsNotNone(self._browse_item_for(self.fn), "編集済みのはずが「編集済みのみ表示」で消えている")

    def test_clearing_image_unmarks_browse_list_item(self):
        self._add_as_target()
        png_path = os.path.join(self.tmp, "custom.png")
        Image.new("RGBA", (16, 16), (9, 9, 9, 255)).save(png_path)
        self.item.import_image_path(png_path)

        self.item._on_clear_image()

        browse_item = self._browse_item_for(self.fn)
        self.assertFalse(browse_item.text().startswith("●"))

    def test_browse_selection_survives_reload(self):
        """一覧の作り直し（●マーク更新）で、選択中の項目が見失われないこと。"""
        self._add_as_target()
        png_path = os.path.join(self.tmp, "custom.png")
        Image.new("RGBA", (16, 16), (9, 9, 9, 255)).save(png_path)

        browse_item = self._browse_item_for(self.fn)
        browse_item.setSelected(True)

        self.item.import_image_path(png_path)  # 内部で一覧が作り直される

        browse_item_after = self._browse_item_for(self.fn)
        self.assertTrue(browse_item_after.isSelected())


class TestPixelEditorRevertToOriginal(unittest.TestCase):
    def setUp(self):
        silence_dialogs()
        self.window, self.bt, self.tmp, self.block_dir, self.out = make_ready_window("RevertTest")
        self.item = self.window.item_tab
        self.fn = sorted(os.listdir(self.item.items_dir))[0]
        self.item.target_items.append({
            "filename": self.fn, "path": os.path.join(self.item.items_dir, self.fn),
        })
        self.item._refresh_target_list()
        self.item._current_filename = self.fn
        self.item._effect_target_filenames = [self.fn]

    def test_clear_after_pixel_edit_restores_true_original_bytes(self):
        """
        ドット絵エディタで描いた後でも、「外部PNG画像を解除」で
        本当にオリジナルのファイル（ディスク上のテクスチャ）へ戻ること。
        ドット絵エディタは常にメモリ上のPIL Imageだけを操作しており、
        元ファイル自体を書き換えることは無いので、いつでも可逆のはず。
        """
        from item_texture_editor import PixelEditDialog
        from PyQt6.QtWidgets import QDialog, QInputDialog

        original_path = os.path.join(self.item.items_dir, self.fn)
        original_bytes = Image.open(original_path).convert("RGBA").tobytes()

        drawn = Image.new("RGBA", (64, 64), (255, 0, 0, 255))
        original_exec = PixelEditDialog.exec
        original_get_item = QInputDialog.getItem

        def fake_exec(self):
            self.result_image = drawn
            return QDialog.DialogCode.Accepted

        PixelEditDialog.exec = fake_exec
        QInputDialog.getItem = staticmethod(lambda *a, **k: ("64", True))
        try:
            self.item._on_open_pixel_editor()
        finally:
            PixelEditDialog.exec = original_exec
            QInputDialog.getItem = original_get_item

        # ドット絵エディタでの編集が確かに反映されていること
        cfg = self.item.item_configs[self.fn]
        self.assertIsNotNone(cfg["custom_image"])
        base_after_edit = self.item._base_image_for(self.fn)
        self.assertEqual(base_after_edit.tobytes(), drawn.convert("RGBA").tobytes())

        # 「外部PNG画像を解除（オリジナルに戻す）」で本当にオリジナルへ戻ること
        self.item._on_clear_image()
        self.assertIsNone(self.item.item_configs[self.fn]["custom_image"])
        base_after_clear = self.item._base_image_for(self.fn)
        self.assertEqual(base_after_clear.tobytes(), original_bytes)


if __name__ == "__main__":
    unittest.main()
