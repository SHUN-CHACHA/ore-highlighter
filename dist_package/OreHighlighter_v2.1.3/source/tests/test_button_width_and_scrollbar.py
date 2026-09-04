"""
ボタンの横幅・中央揃え・スクロールバーの視認性に関するテスト。

背景:
  各タブをQScrollAreaに収めて最小サイズを切り離すようにしたところ、
  実機（Windows）でスプリッタやウィンドウを縮めた際に、ボタンの横幅まで
  レイアウトに押し縮められてしまい、文字が中央からずれたり、文字の
  右端が欠けて見える不具合が実際に報告された。

  対策として ui_utils.fix_button_widths() を全タブの構築処理の最後に
  呼び、各ボタン・コンボボックスに sizeHint() 分の最小幅を明示的に
  設定した。あわせて ui_utils.SCROLLBAR_QSS をアプリ全体の
  スタイルシートに組み込み、スクロールバーを太く・つまみを大きくした。
"""

import unittest

from helpers import make_window
from PyQt6.QtWidgets import QPushButton, QComboBox
import main as M
from ui_utils import SCROLLBAR_QSS


class TestButtonMinimumWidths(unittest.TestCase):
    """全タブのボタン・コンボボックスが sizeHint() 未満に縮まないこと。"""

    def setUp(self):
        self.window = make_window()

    QWIDGETSIZE_MAX = 16777215  # Qtの「制約なし」を表す既定の最大サイズ

    def _assert_no_button_shrinks_below_hint(self, container, label):
        for btn in container.findChildren(QPushButton):
            # 十字キーの移動ボタンや色スウォッチのように setFixedSize() 済みの
            # ボタンは、意図的にsizeHintより小さい正方形にしているので対象外。
            if (btn.minimumWidth() == btn.maximumWidth()
                    and btn.maximumWidth() < self.QWIDGETSIZE_MAX):
                continue
            hint_w = btn.sizeHint().width()
            if hint_w <= 0:
                continue
            self.assertGreaterEqual(
                btn.minimumWidth(), hint_w,
                f"{label}: ボタン「{btn.text()}」の最小幅がsizeHintより小さい "
                f"(minimumWidth={btn.minimumWidth()}, sizeHint={hint_w})",
            )

    def _assert_no_combo_shrinks_below_hint(self, container, label):
        for combo in container.findChildren(QComboBox):
            hint_w = combo.sizeHint().width()
            if hint_w <= 0:
                continue
            self.assertGreaterEqual(
                combo.minimumWidth(), hint_w,
                f"{label}: コンボボックスの最小幅がsizeHintより小さい "
                f"(minimumWidth={combo.minimumWidth()}, sizeHint={hint_w})",
            )

    def test_block_tab_buttons_have_enforced_minimum_width(self):
        self._assert_no_button_shrinks_below_hint(self.window.block_tab, "ブロックエフェクトタブ")
        self._assert_no_combo_shrinks_below_hint(self.window.block_tab, "ブロックエフェクトタブ")

    def test_output_settings_tab_buttons_have_enforced_minimum_width(self):
        self._assert_no_button_shrinks_below_hint(
            self.window.block_tab.output_settings_tab, "出力設定タブ"
        )
        self._assert_no_combo_shrinks_below_hint(
            self.window.block_tab.output_settings_tab, "出力設定タブ"
        )

    def test_gui_icon_tab_buttons_have_enforced_minimum_width(self):
        self._assert_no_button_shrinks_below_hint(self.window.gui_icon_tab, "GUIアイコン編集タブ")

    def test_item_tab_buttons_have_enforced_minimum_width(self):
        self._assert_no_button_shrinks_below_hint(self.window.item_tab, "アイテムテクスチャ編集タブ")


class TestScrollbarStylesheetApplied(unittest.TestCase):
    """スクロールバーを太く・つまみを大きくするQSSが、アプリ全体に適用されていること。"""

    def test_scrollbar_qss_is_part_of_global_button_stylesheet(self):
        self.assertIn("QScrollBar", M.BUTTON_STYLESHEET)
        self.assertIn(SCROLLBAR_QSS.strip(), M.BUTTON_STYLESHEET)

    def test_scrollbar_qss_defines_wider_bars_and_bigger_handles(self):
        self.assertIn("width: 20px", SCROLLBAR_QSS)
        self.assertIn("height: 20px", SCROLLBAR_QSS)
        self.assertIn("min-height: 40px", SCROLLBAR_QSS)
        self.assertIn("min-width: 40px", SCROLLBAR_QSS)


if __name__ == "__main__":
    unittest.main()
