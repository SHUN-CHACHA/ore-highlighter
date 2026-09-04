"""
ウィンドウ・各タブの最小サイズに関するテスト。

背景:
  ブロックエフェクトタブは3分割（テクスチャ一覧・対象ブロック・編集エリア）の
  スプリッタで、左右パネルの中身（ボタン・フォームラベル等）が要求する幅が
  大きく、手動でスプリッタを縮めてもそこで頭打ちになっていた。
  さらに、GUIアイコン編集タブ（QColorDialogを丸ごと埋め込んでいる）と
  アイテムテクスチャ編集タブは、それぞれの中身がQScrollAreaに収まっておらず、
  その大きな最小サイズが（QTabWidgetの仕様上）タブの切り替えに関わらず
  ウィンドウ全体の最小サイズに伝播してしまい、1920×1080の画面でも
  余裕なく表示される・それ以上縮められない、という問題があった。

  対策として、ブロックエフェクトタブの3パネルと、GUIアイコン編集・
  アイテムテクスチャ編集タブの中身をそれぞれQScrollAreaに収め、
  タブ自身の最小サイズをコンテンツの量から切り離した。
"""

import unittest

from helpers import make_window
from PyQt6.QtWidgets import QScrollArea


class TestWindowMinimumSize(unittest.TestCase):
    def setUp(self):
        self.window = make_window()
        self.window.show()

    def test_window_minimum_size_fits_comfortably_in_1920x1080(self):
        """
        1920×1080の画面でも周囲に余裕を持って表示できるよう、
        ウィンドウの最小サイズは十分小さいこと（タブ切り替えに関わらず）。
        """
        for i in range(self.window.tabs.count()):
            self.window.tabs.setCurrentIndex(i)
            size = self.window.minimumSizeHint()
            self.assertLess(
                size.width(), 1920 - 300,
                f"タブ{i}（{self.window.tabs.tabText(i)}）表示中、ウィンドウの最小幅が大きすぎる: {size}",
            )
            self.assertLess(
                size.height(), 1080 - 200,
                f"タブ{i}（{self.window.tabs.tabText(i)}）表示中、ウィンドウの最小高さが大きすぎる: {size}",
            )

    def test_default_window_size_is_smaller_than_1920x1080(self):
        """main.py起動直後の既定サイズ自体も、1920×1080に余裕を持って収まること。"""
        self.assertLess(self.window.width(), 1920 - 200)
        self.assertLess(self.window.height(), 1080 - 150)


class TestBlockTabPanelsCanShrink(unittest.TestCase):
    def setUp(self):
        self.window = make_window()

    def test_three_panels_are_wrapped_in_scroll_areas(self):
        scroll_areas = self.window.block_tab.findChildren(QScrollArea)
        self.assertEqual(len(scroll_areas), 3, "ブロックエフェクトタブの3パネルがQScrollAreaに収まっていない")

    def test_side_panels_minimum_width_is_small(self):
        scroll_areas = self.window.block_tab.findChildren(QScrollArea)
        widths = sorted(sa.minimumWidth() for sa in scroll_areas)
        # 以前は（内容量依存で）600px近くまで縮められなかった箇所がある想定。
        # 明示的に設定した180/160/220のいずれよりも小さいはずが無いが、大きすぎもしないこと。
        for w in widths:
            self.assertLessEqual(w, 250, f"パネルの最小幅がまだ大きい: {w}")


class TestGuiIconAndItemTabsWrappedInScrollArea(unittest.TestCase):
    def setUp(self):
        self.window = make_window()

    def test_gui_icon_tab_wrapped_in_scroll_area(self):
        scroll_areas = self.window.gui_icon_tab.findChildren(QScrollArea)
        self.assertGreaterEqual(len(scroll_areas), 1)

    def test_item_tab_wrapped_in_scroll_area(self):
        scroll_areas = self.window.item_tab.findChildren(QScrollArea)
        self.assertGreaterEqual(len(scroll_areas), 1)

    def test_gui_icon_tab_minimum_size_is_small(self):
        """QScrollAreaに収めたタブ自体の最小サイズは小さいこと。"""
        size = self.window.gui_icon_tab.minimumSizeHint()
        self.assertLess(size.width(), 300)
        self.assertLess(size.height(), 300)

    def test_gui_icon_tab_content_itself_is_compact(self):
        """
        QScrollAreaでウィンドウから切り離しただけでは、中身自体が大きいままだと
        実際にウィンドウを縮めたときに横スクロールが必要になってしまう。
        色パネルを軽量なCompactColorPickerに置き換えたことで、
        QScrollAreaの中身（content）自体の横幅も十分小さいこと。
        """
        scroll = self.window.gui_icon_tab.findChild(QScrollArea)
        content = scroll.widget()
        self.assertLess(
            content.sizeHint().width(), 1300,
            f"GUIアイコン編集タブの中身自体がまだ大きい: {content.sizeHint()}",
        )


if __name__ == "__main__":
    unittest.main()
