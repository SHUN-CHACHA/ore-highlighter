"""
アイテムテクスチャ編集タブの「確定フィードバック」表示のテスト。

背景:
  アイテムテクスチャ編集は、GUIアイコン編集と違って「保存する」ボタンを持たない。
  外部PNG画像を選ぶ／ドット絵エディタで「保存して閉じる」を押す、その瞬間に
  item_configs へ即座に反映される設計（下書き状態を持たない）。
  ただしボタンが無いことで「今の操作が反映されたのか」がユーザーから見えにくかったため、
  status_label に一言表示するようにした。

  「編集内容が実際に保存されているか」自体は、既存の test_cross_pc_portability.py /
  test_pack_generation.py 側で（config.json・生成パックへの反映という形で）
  既に検証済み。ここではあくまで「操作した直後にフィードバックが出ること」を確認する。
"""

import os
import unittest

from helpers import make_ready_window, silence_dialogs  # noqa: F401
from PIL import Image


class TestItemStatusFeedback(unittest.TestCase):
    def setUp(self):
        silence_dialogs()
        self.window, self.bt, self.tmp, self.block_dir, self.out = make_ready_window("StatusTest")
        self.item = self.window.item_tab
        self.fn = sorted(os.listdir(self.item.items_dir))[0]
        self.item.target_items.append({
            "filename": self.fn, "path": os.path.join(self.item.items_dir, self.fn),
        })
        self.item._refresh_target_list()
        self.item._current_filename = self.fn
        self.item._effect_target_filenames = [self.fn]

    def test_status_label_exists_and_starts_empty(self):
        self.assertTrue(hasattr(self.item, "status_label"))
        self.assertEqual(self.item.status_label.text(), "")

    def test_choosing_external_image_shows_feedback(self):
        png_path = os.path.join(self.tmp, "custom.png")
        Image.new("RGBA", (16, 16), (1, 2, 3, 255)).save(png_path)

        ok = self.item.import_image_path(png_path)

        self.assertTrue(ok)
        self.assertIn(self.fn, self.item.status_label.text())
        self.assertIn("反映", self.item.status_label.text())

    def test_clearing_image_shows_feedback(self):
        png_path = os.path.join(self.tmp, "custom.png")
        Image.new("RGBA", (16, 16), (1, 2, 3, 255)).save(png_path)
        self.item.import_image_path(png_path)

        self.item._on_clear_image()

        self.assertIn(self.fn, self.item.status_label.text())
        self.assertIn("解除", self.item.status_label.text())
        self.assertIsNone(self.item.item_configs[self.fn]["custom_image"])

    def test_pixel_editor_save_shows_feedback(self):
        """
        PixelEditDialog は本来モーダルで開くが、テストでは実際にダイアログを
        操作する代わりに「保存して閉じる」を押した場合と同じ状態
        （dialog.exec()がAcceptedを返し、result_imageがセット済み）を模擬する。

        作業解像度を選ぶ QInputDialog も同様にモーダルなので、あわせてモックする
        （モックし忘れると、画面の無いテスト環境ではexec()が永久に返ってこない）。
        """
        from item_texture_editor import PixelEditDialog
        from PyQt6.QtWidgets import QDialog, QInputDialog

        drawn = Image.new("RGBA", (64, 64), (5, 6, 7, 255))
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

        self.assertIn(self.fn, self.item.status_label.text())
        self.assertIn("反映", self.item.status_label.text())
        self.assertIsNotNone(self.item.item_configs[self.fn]["custom_image"])


if __name__ == "__main__":
    unittest.main()
