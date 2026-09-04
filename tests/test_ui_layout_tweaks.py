"""
実機スクリーンショットを受けてのUI配置調整に関するテスト。

要望（v2.0.2以降の未リリース分）:
  1. ブロックエフェクトタブのテクスチャ一覧は縦に広げてよい
     （「読み込み」タブ分離で縦に余裕ができたため、10行の頭打ちを外す）
  2. GUIアイコン編集タブの「外部PNGをインポート...」は中央列（キャンバスの列）の最下部へ
  3. アイテムテクスチャ編集タブの「アニメーションプレビュー」は中央列（対象アイテムの列）へ
  4. アイテムの外部PNGに関する注意事項3件は、プレビュー枠の横のボタンに集約し
     マウスオーバーでフローティング表示する
"""

import unittest

from helpers import make_window, get_app  # noqa: F401
from ui_utils import NoticeButton
from PyQt6.QtWidgets import QGroupBox, QLabel


def containing_layout(widget):
    """widget を直接載せているレイアウトを、入れ子をたどって探す。

    列（QVBoxLayout）は親ウィジェットを持たないサブレイアウトなので、
    widget.parentWidget().layout() だけでは一番外側しか取れない。
    """
    root = widget.parentWidget().layout() if widget.parentWidget() else None
    if root is None:
        return None

    def walk(layout):
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item.widget() is widget:
                return layout
            child = item.layout()
            if child is not None:
                found = walk(child)
                if found is not None:
                    return found
        return None

    return walk(root)


def widgets_in(layout):
    return [layout.itemAt(i).widget() for i in range(layout.count())]


class TestBlockBrowseListCanGrow(unittest.TestCase):
    def test_no_height_cap_on_texture_list(self):
        """縦の頭打ちが外れていること（Qtの既定の最大値のまま＝制限なし）。"""
        w = make_window()
        browse = w.block_tab.browse_list
        self.assertGreater(browse.maximumHeight(), 10000,
                           "テクスチャ一覧にまだ高さの上限が掛かっている")

    def test_texture_list_takes_the_spare_height(self):
        """余った高さは一覧に配分されること（上のラベルが間延びしないように）。"""
        w = make_window()
        bt = w.block_tab
        layout = containing_layout(bt.browse_list)
        index = layout.indexOf(bt.browse_list)
        self.assertGreater(layout.stretch(index), 0,
                           "一覧に stretch が付いていないので余白の行き先が定まらない")


class TestGuiIconImportButtonMoved(unittest.TestCase):
    def setUp(self):
        self.window = make_window()
        self.gt = self.window.gui_icon_tab

    def test_import_button_is_in_the_canvas_column(self):
        """キャンバスと同じ列（中央列）に移動していること。"""
        btn_layout = containing_layout(self.gt.import_png_btn)
        canvas_layout = containing_layout(self.gt.canvas)
        self.assertIsNotNone(btn_layout, "インポートボタンがレイアウトに載っていない")
        # キャンバスは中央列の中の横並び行に入っているので、その親レイアウトと比べる
        self.assertIs(btn_layout, canvas_layout.parent(),
                      "インポートボタンがキャンバスと同じ列に無い")

    def test_import_button_is_below_the_top_button_rows(self):
        """保存する/コピー・ペーストなど上部のボタン群のすぐ下、キャンバスより上に来ていること。"""
        center = containing_layout(self.gt.import_png_btn)
        self.assertIs(center, containing_layout(self.gt.dirty_indicator),
                      "インポートボタンが上部ボタン群と同じ列（中央列直下）に無い")

        copy_paste_row = containing_layout(self.gt.copy_btn)
        copy_row_index = None
        for i in range(center.count()):
            if center.itemAt(i).layout() is copy_paste_row:
                copy_row_index = i
                break
        self.assertIsNotNone(copy_row_index, "コピー/ペースト行が見つからない")

        btn_index = center.indexOf(self.gt.import_png_btn)
        onion_index = center.indexOf(self.gt.onion_skin_checkbox)
        self.assertGreater(btn_index, copy_row_index,
                           "インポートボタンが保存する/コピー・ペースト行より上に無いこと")
        self.assertLess(btn_index, onion_index,
                        "インポートボタンがキャンバス側（オニオンスキン以降）まで下がっていないこと")

    def test_old_io_group_is_gone(self):
        titles = [g.title() for g in self.gt.findChildren(QGroupBox)]
        self.assertNotIn("画像の入出力", titles,
                         "右列の「画像の入出力」グループが残っている")


class TestItemPreviewMoved(unittest.TestCase):
    def test_animation_preview_is_in_the_target_list_column(self):
        w = make_window()
        it = w.item_tab
        preview_group = None
        for g in it.findChildren(QGroupBox):
            if g.title() == "アニメーションプレビュー":
                preview_group = g
                break
        self.assertIsNotNone(preview_group, "アニメーションプレビューが見つからない")

        # 対象アイテム一覧と同じレイアウトに載っていること（＝中央列）
        self.assertIn(preview_group, widgets_in(containing_layout(it.target_list)),
                      "アニメーションプレビューが中央列（対象アイテムの列）に無い")

    def test_target_list_still_takes_the_spare_height(self):
        w = make_window()
        it = w.item_tab
        layout = containing_layout(it.target_list)
        index = layout.indexOf(it.target_list)
        self.assertGreater(layout.stretch(index), 0,
                           "対象アイテム一覧に stretch が無いとプレビューが下に落ち着かない")


class TestItemNoticeButton(unittest.TestCase):
    def test_notice_button_replaces_the_always_visible_text(self):
        w = make_window()
        it = w.item_tab
        self.assertIsInstance(it.notice_btn, NoticeButton)

        # 以前の常時表示ラベルが残っていないこと
        for label in it.findChildren(QLabel):
            self.assertNotIn("正方形・512×512px以下", label.text(),
                             "注意事項の常時表示ラベルがまだ残っている")

    def test_notice_button_holds_all_four_notices(self):
        w = make_window()
        html = w.item_tab.notice_btn.toolTip()
        self.assertIn("正方形", html)
        self.assertIn("半透明ピクセル", html)
        self.assertIn("64px以下", html)
        self.assertIn("2のべき乗", html)

    def test_notice_button_sits_next_to_the_previews(self):
        """プレビュー枠と同じ列（＝同じ親ウィジェット）に置かれていること。"""
        w = make_window()
        it = w.item_tab
        notice_layout = containing_layout(it.notice_btn)
        preview_layout = containing_layout(it.custom_preview)
        self.assertIs(notice_layout.parent(), preview_layout.parent(),
                      "注意事項ボタンがプレビュー枠の横（同じ行）に無い")

    def test_set_notices_updates_the_tooltip(self):
        get_app()
        btn = NoticeButton(notices=["ひとつめ"])
        self.assertIn("ひとつめ", btn.toolTip())
        btn.set_notices(["ふたつめ", "みっつめ"])
        self.assertNotIn("ひとつめ", btn.toolTip())
        self.assertIn("みっつめ", btn.toolTip())


if __name__ == "__main__":
    unittest.main()
