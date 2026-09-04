"""
ドット絵エディタの共通化（pixel_editor.py）に関するテスト。

背景:
  キャンバス本体（PixelCanvas）は共有されていたが、周辺UI（ペン/バケツ/スポイトの
  切り替え）は GUIアイコン編集タブとアイテムのダイアログで別々に書かれていた。
  さらに PixelEditDialog は item_texture_editor.py の中にあり、
  gui_icon_editor.py を import していた（タブ同士が依存し合う状態）。

  pixel_editor.py に集約し、両者が同じ ToolSelector / PixelCanvas /
  PixelEditDialog を使うようにした。
"""

import unittest

from helpers import make_window, get_app  # noqa: F401
from pixel_editor import PixelCanvas, ToolSelector, PixelEditDialog, CompactColorPicker
from PyQt6.QtGui import QColor
from PIL import Image


class TestToolSelector(unittest.TestCase):
    def setUp(self):
        get_app()

    def test_pen_is_selected_by_default(self):
        sel = ToolSelector()
        self.assertEqual(sel.current_tool(), "pen")

    def test_select_switches_exclusively(self):
        sel = ToolSelector()
        sel.select("bucket")
        self.assertEqual(sel.current_tool(), "bucket")
        self.assertFalse(sel.buttons["pen"].isChecked())

    def test_select_does_not_emit(self):
        """select() は「表示を合わせる」ためのものなので、シグナルは出さない
        （出すとクリック→選択→再クリック相当のループになりかねない）。"""
        sel = ToolSelector()
        emitted = []
        sel.tool_changed.connect(emitted.append)
        sel.select("eyedropper")
        self.assertEqual(emitted, [])

    def test_clicking_a_button_emits_the_key(self):
        sel = ToolSelector()
        emitted = []
        sel.tool_changed.connect(emitted.append)
        sel.buttons["bucket"].click()
        self.assertEqual(emitted, ["bucket"])


class TestBothEditorsShareTheParts(unittest.TestCase):
    def test_gui_icon_tab_uses_shared_tool_selector(self):
        w = make_window()
        gt = w.gui_icon_tab
        self.assertIsInstance(gt.tool_selector, ToolSelector)
        self.assertIsInstance(gt.canvas, PixelCanvas)
        # 既存コードとの互換で tool_buttons も残している
        self.assertIs(gt.tool_buttons, gt.tool_selector.buttons)

    def test_gui_icon_tool_selection_reaches_the_canvas(self):
        w = make_window()
        gt = w.gui_icon_tab
        gt.tool_buttons["bucket"].click()
        self.assertEqual(gt.canvas.tool, "bucket")
        self.assertEqual(gt.tool_selector.current_tool(), "bucket")

    def test_item_dialog_uses_shared_tool_selector(self):
        w = make_window()
        dlg = PixelEditDialog(w, size=16)
        self.assertIsInstance(dlg.tool_selector, ToolSelector)
        dlg.tool_buttons["eyedropper"].click()
        self.assertEqual(dlg.canvas.tool, "eyedropper")

    def test_item_texture_editor_reexports_the_dialog(self):
        """テストや既存コードが item_texture_editor 経由で参照しても、
        実体は pixel_editor 側の同じクラスであること。"""
        import item_texture_editor as ITE
        self.assertIs(ITE.PixelEditDialog, PixelEditDialog)

    def test_gui_icon_editor_reexports_the_canvas(self):
        import gui_icon_editor as GIE
        self.assertIs(GIE.PixelCanvas, PixelCanvas)


class TestCompactColorPicker(unittest.TestCase):
    """埋め込みQColorDialogを置き換えた軽量な色選択ウィジェットのテスト。"""

    def test_default_current_color(self):
        get_app()
        picker = CompactColorPicker()
        self.assertTrue(picker.current_color().isValid())

    def test_clicking_a_preset_swatch_changes_current_color_and_emits(self):
        get_app()
        picker = CompactColorPicker()
        received = []
        picker.currentColorChanged.connect(lambda c: received.append(c))
        grid = picker.layout().itemAt(0).layout()
        first_swatch = grid.itemAt(0).widget()
        first_swatch.click()
        self.assertEqual(len(received), 1)
        self.assertEqual(picker.current_color().name(), received[0].name())

    def test_set_current_color_without_emit_does_not_fire_signal(self):
        get_app()
        picker = CompactColorPicker()
        received = []
        picker.currentColorChanged.connect(lambda c: received.append(c))
        picker.set_current_color(QColor(10, 20, 30, 255), emit=False)
        self.assertEqual(len(received), 0)
        self.assertEqual(picker.current_color().getRgb(), (10, 20, 30, 255))

    def test_preset_swatches_stay_at_their_fixed_small_size(self):
        """fix_button_widths() を後から掛けても、スウォッチの正方形サイズが崩れないこと。"""
        w = make_window()
        gt = w.gui_icon_tab
        grid = gt.color_picker.layout().itemAt(0).layout()
        first_swatch = grid.itemAt(0).widget()
        self.assertEqual(first_swatch.minimumWidth(), first_swatch.maximumWidth())
        self.assertLessEqual(first_swatch.minimumWidth(), 24)

    def test_gui_icon_tab_uses_the_compact_picker(self):
        w = make_window()
        gt = w.gui_icon_tab
        self.assertIsInstance(gt.color_picker, CompactColorPicker)

    def test_picking_a_color_on_the_canvas_updates_the_picker_without_a_loop(self):
        """スポイトで拾った色がピッカーに反映されること（無限ループにならないこと）。"""
        w = make_window()
        gt = w.gui_icon_tab
        gt._on_color_picked((11, 22, 33, 255))
        self.assertEqual(gt.color_picker.current_color().getRgb(), (11, 22, 33, 255))
        self.assertEqual(gt.canvas.current_color, (11, 22, 33, 255))


class TestPixelEditDialogMatchesGuiIconEditor(unittest.TestCase):
    """
    アイテムテクスチャ編集の「ドット絵エディタ」を、GUIアイコン編集タブと同じ
    色パレット（CompactColorPicker）・編集中プレビュー・オニオンスキン表示に
    揃えたことの回帰テスト。
    """

    def test_uses_the_compact_color_picker(self):
        w = make_window()
        dlg = PixelEditDialog(w, size=16)
        self.assertIsInstance(dlg.color_picker, CompactColorPicker)

    def test_choosing_a_color_reaches_the_canvas(self):
        w = make_window()
        dlg = PixelEditDialog(w, size=16)
        dlg.color_picker.set_current_color(QColor(11, 22, 33, 255))
        self.assertEqual(dlg.canvas.current_color, (11, 22, 33, 255))

    def test_eyedropper_pick_updates_the_picker_without_a_loop(self):
        w = make_window()
        dlg = PixelEditDialog(w, size=16)
        dlg._on_color_picked((44, 55, 66, 255))
        self.assertEqual(dlg.color_picker.current_color().getRgb(), (44, 55, 66, 255))
        self.assertEqual(dlg.canvas.current_color, (44, 55, 66, 255))

    def test_edit_preview_starts_empty(self):
        w = make_window()
        dlg = PixelEditDialog(w, size=16)
        self.assertEqual(dlg.edit_preview.text(), "（空）")

    def test_edit_preview_updates_when_the_canvas_changes(self):
        w = make_window()
        dlg = PixelEditDialog(w, size=16)
        dlg.canvas.set_color((200, 0, 0, 255))
        dlg.canvas.pixels[0][0] = (200, 0, 0, 255)
        dlg.canvas.changed.emit()
        self.assertFalse(dlg.edit_preview.pixmap().isNull())

    def test_onion_skin_checkbox_is_disabled_without_an_original_image(self):
        w = make_window()
        dlg = PixelEditDialog(w, size=16, original_image=None)
        self.assertFalse(dlg.onion_skin_checkbox.isEnabled())

    def test_onion_skin_checkbox_is_enabled_with_an_original_image(self):
        w = make_window()
        original = Image.new("RGBA", (16, 16), (10, 20, 30, 255))
        dlg = PixelEditDialog(w, size=16, original_image=original)
        self.assertTrue(dlg.onion_skin_checkbox.isEnabled())

    def test_checking_onion_skin_sets_it_on_the_canvas(self):
        w = make_window()
        original = Image.new("RGBA", (16, 16), (10, 20, 30, 255))
        dlg = PixelEditDialog(w, size=16, original_image=original)
        dlg.onion_skin_checkbox.setChecked(True)
        self.assertIsNotNone(dlg.canvas._onion_skin)

    def test_unchecking_onion_skin_clears_it_from_the_canvas(self):
        w = make_window()
        original = Image.new("RGBA", (16, 16), (10, 20, 30, 255))
        dlg = PixelEditDialog(w, size=16, original_image=original)
        dlg.onion_skin_checkbox.setChecked(True)
        dlg.onion_skin_checkbox.setChecked(False)
        self.assertIsNone(dlg.canvas._onion_skin)


class TestPixelEditDialogPostProcess(unittest.TestCase):
    """保存時の後処理（アイテムの二値化）は呼び出し側から差し込む形にした。"""

    def test_post_process_is_applied_on_save(self):
        w = make_window()
        marker = Image.new("RGBA", (4, 4), (1, 2, 3, 255))
        dlg = PixelEditDialog(w, size=4, post_process=lambda img: marker)
        dlg._on_save()
        self.assertIs(dlg.result_image, marker)

    def test_without_post_process_the_canvas_image_is_used(self):
        w = make_window()
        dlg = PixelEditDialog(w, size=4)
        dlg._on_save()
        self.assertIsNotNone(dlg.result_image)
        self.assertEqual(dlg.result_image.size, (4, 4))


if __name__ == "__main__":
    unittest.main()
