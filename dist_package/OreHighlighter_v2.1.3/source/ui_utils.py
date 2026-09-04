"""
GUI全体で共通して使う、小さな見た目調整のユーティリティ。

背景:
  各タブの中身をQScrollAreaに収めて「タブ自体の最小サイズ」を
  切り離すようにしたところ、スプリッタやウィンドウを縮めた際に、
  ボタンやコンボボックスの横幅までレイアウトに押し縮められてしまい、
  文字が中央に来なくなったり、テキストの右端が欠けて見える不具合が
  起きた。

  原因: QPushButton / QComboBox は既定では「文字がぎりぎり収まる幅」を
  レイアウト上の最小幅として保証してくれない（sizeHint()は文字幅込みだが、
  レイアウトが実際に使う最小幅はそれとは独立に0近くまで縮められる）。

  対策: 各パネルを組み立てた直後に fix_button_widths() を呼び、その
  パネル内の全ボタン・コンボボックスに「これ以上は縮めない」という
  最小幅を明示的に設定する。パネル自体がそれでも入りきらない幅まで
  縮められた場合は、（ボタンの文字が欠けるのではなく）QScrollAreaの
  横スクロールバーで中身を見られるようにする。

  あわせて、SCROLLBAR_QSS をアプリ全体に適用し、スクロールバー自体も
  太く・つまみを大きくして、「一番下や右端にまだ内容がある」ことに
  気づきやすくしている（全タブ共通）。
"""

from PyQt6.QtWidgets import QPushButton, QComboBox, QToolTip
from PyQt6.QtCore import QPoint


def fix_button_widths(widget, extra_px=8):
    """
    widget配下の全QPushButton/QComboBoxに、内容（文字）が欠けたり
    中央からずれたりしない最小幅を保証する。

    パネルを一通り組み立て終えた直後（_build_ui()の最後など）に
    1回呼べば、そのパネル内の全ボタン・コンボボックスに再帰的に効く。

    【注意】十字キーの移動ボタンや色スウォッチのように、setFixedSize()で
    意図的に小さい正方形にしているボタンまで広げてしまうと、その分だけ
    パネル全体の最小幅が無駄に大きくなる。すでに幅が固定されている
    （setFixedSize済み＝最小幅と最大幅が一致している）ボタンは対象から
    除外し、意図したサイズのままにする。
    """
    QWIDGETSIZE_MAX = 16777215  # Qtの「制約なし」を表す既定の最大サイズ
    for btn in widget.findChildren(QPushButton):
        if btn.minimumWidth() == btn.maximumWidth() and btn.maximumWidth() < QWIDGETSIZE_MAX:
            continue  # setFixedSize済み（意図的な固定サイズ）は触らない
        hint = btn.sizeHint().width()
        if hint > 0:
            btn.setMinimumWidth(hint + extra_px)
    for combo in widget.findChildren(QComboBox):
        hint = combo.sizeHint().width()
        if hint > 0:
            combo.setMinimumWidth(hint)


# 縦・横ともに太く、つまみ（ノブ）も大きく見やすいスクロールバー。
# 「一番下にまだボタンがあるのに気づきにくい」という指摘への対応。
# QApplication.setStyleSheet() に連結して使うことで、全タブ・全ダイアログの
# QScrollArea / QListWidget / QTextEdit 等に共通で効く。
SCROLLBAR_QSS = """
QScrollBar:vertical {
    width: 20px;
    background: #e8e8e8;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #949ba3;
    min-height: 40px;
    border-radius: 7px;
    margin: 2px;
}
QScrollBar::handle:vertical:hover {
    background: #6f7680;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
    border: none;
    background: none;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
}

QScrollBar:horizontal {
    height: 20px;
    background: #e8e8e8;
    margin: 0px;
}
QScrollBar::handle:horizontal {
    background: #949ba3;
    min-width: 40px;
    border-radius: 7px;
    margin: 2px;
}
QScrollBar::handle:horizontal:hover {
    background: #6f7680;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
    border: none;
    background: none;
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: none;
}
"""


class NoticeButton(QPushButton):
    """マウスを載せている間だけ、注意事項をフローティング枠に表示するボタン。

    長い注意文を画面に常時置いておくと、その分だけ操作に使う領域が狭くなり、
    毎回読むわけでもないのに目立ち続けてしまう。かといって消してしまうと
    「正方形しか受け付けない」等の制約に気づけない。そこで、普段は小さな
    ボタンだけを置き、マウスオーバー（またはクリック）で内容を出す形にした。

    表示にはQtのツールチップの仕組みをそのまま使う（＝OS標準の
    フローティング枠なので、ウィンドウの端でも自動で位置が調整される）。
    既定のツールチップは表示までに間があるので、enterEvent で即座に出す。
    """

    def __init__(self, text="⚠ 注意事項", notices=(), parent=None):
        super().__init__(text, parent)
        self._notices = list(notices)
        # 注意書きだと一目で分かるよう、黄色地＋黒の外枠＋黒文字にする。
        # （淡い色の文字だけだと、他のボタンに埋もれて気づかれない）
        self.setStyleSheet(
            "QPushButton {"
            "  background-color: #ffd633;"
            "  color: #000000;"
            "  font-weight: bold;"
            "  border: 2px solid #000000;"
            "  border-radius: 4px;"
            "  padding: 4px 10px;"
            "}"
            "QPushButton:hover { background-color: #ffe066; }"
            "QPushButton:pressed { background-color: #f0c200; }"
        )
        # マウスオーバーを待たずに知りたい人のために、クリックでも同じものを出す
        self.clicked.connect(self._show_notices)
        # 標準のツールチップも設定しておく（キーボード操作や、
        # enterEvent が来ない環境でのフォールバック）
        self.setToolTip(self._html())

    def set_notices(self, notices):
        self._notices = list(notices)
        self.setToolTip(self._html())

    def _html(self):
        items = "".join(f"<li style='margin-bottom:6px;'>{n}</li>" for n in self._notices)
        return f"<div style='max-width:420px;'><ul style='margin-left:-20px;'>{items}</ul></div>"

    def _show_notices(self):
        # ボタンの真下に出す（枠が画面外に出る場合はQt側が自動で寄せてくれる）
        QToolTip.showText(self.mapToGlobal(QPoint(0, self.height())), self._html(), self)

    def enterEvent(self, event):
        self._show_notices()
        super().enterEvent(event)

    def leaveEvent(self, event):
        QToolTip.hideText()
        super().leaveEvent(event)
