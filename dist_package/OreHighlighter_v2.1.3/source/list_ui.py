"""
一覧まわりの共通部品（絞り込みフィルタ・編集済みマーク・削除の確認とUndo）。

【なぜこのモジュールがあるか】
ブロックエフェクト／GUIアイコン編集／アイテムテクスチャ編集の3タブは、
どれも「一覧から選んで対象に加え、編集し、いらなくなったら消す」という同じ形をしていて、
以下がそれぞれのファイルに別々に書かれていた:

  - 「編集済みのみ表示」「未編集のみ表示」チェックボックス2つと、その排他制御
    （3ファイルに、変数名だけ違う同一のコードがあった）
  - 検索文字列＋編集済みフィルタの判定
  - 「● / 全角スペース」の編集済みマーク
  - 削除時の確認ダイアログ（共通の注意文＋「削除を元に戻す」の案内）
  - 直近1回分だけ戻せるUndo（記録・ボタンの有効/無効・破棄）

一覧そのもの（何を並べるか・どう表示するか）はタブごとに事情が違うので共通化せず、
「どのタブでも同じであるべき挙動」だけをここに集めている。

Copyright (c) 2026 旬茶
Licensed under the MIT License.
"""

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QCheckBox, QMessageBox
from PyQt6.QtCore import pyqtSignal

EDITED_MARK = "● "
UNEDITED_MARK = "　 "  # 全角スペース。●の分だけ字下げを揃えるためのもの


def marked(is_edited, text):
    """一覧に出す「●付き／字下げだけ」のラベル文字列を作る。"""
    return f"{EDITED_MARK if is_edited else UNEDITED_MARK}{text}"


def matches_filter(query, is_edited, edited_only, unedited_only, *texts):
    """一覧に表示してよいかを判定する。

    query は texts のいずれかに部分一致すればOK（大文字小文字は無視）。
    edited_only / unedited_only は同時にTrueにならない前提（EditedFilterBoxが保証する）。
    """
    if edited_only and not is_edited:
        return False
    if unedited_only and is_edited:
        return False
    if not query:
        return True
    q = query.strip().lower()
    return any(q in (t or "").lower() for t in texts)


class EditedFilterBox(QWidget):
    """「編集済みのみ表示」「未編集のみ表示」の2チェックボックス。

    片方をONにするともう片方は自動でOFFになる（両方ONは矛盾するため）。
    状態が変わると changed を1回だけ出すので、購読側は一覧を作り直せばよい。
    """

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.edited_only_checkbox = QCheckBox("編集済みのみ表示")
        self.unedited_only_checkbox = QCheckBox("未編集のみ表示")
        for cb in (self.edited_only_checkbox, self.unedited_only_checkbox):
            cb.stateChanged.connect(self._on_changed)
            layout.addWidget(cb)
        layout.addStretch(1)

    def _on_changed(self, _state):
        sender = self.sender()
        if sender is self.edited_only_checkbox and self.edited_only_checkbox.isChecked():
            self._set_silently(self.unedited_only_checkbox, False)
        elif sender is self.unedited_only_checkbox and self.unedited_only_checkbox.isChecked():
            self._set_silently(self.edited_only_checkbox, False)
        self.changed.emit()

    @staticmethod
    def _set_silently(checkbox, value):
        checkbox.blockSignals(True)
        checkbox.setChecked(value)
        checkbox.blockSignals(False)

    # --- 購読側から使う窓口 ---
    def edited_only(self):
        return self.edited_only_checkbox.isChecked()

    def unedited_only(self):
        return self.unedited_only_checkbox.isChecked()

    def is_filtering(self):
        """どちらかのフィルタが効いているか（一覧の作り直しが必要かの判定に使う）。"""
        return self.edited_only() or self.unedited_only()

    def accepts(self, query, is_edited, *texts):
        """このフィルタの現在の状態で matches_filter() を評価する。"""
        return matches_filter(query, is_edited, self.edited_only(), self.unedited_only(), *texts)


def confirm_removal(parent, title, count, detail):
    """削除前の確認ダイアログ。文面の骨格（件数・注意文・Undoの案内）は3タブ共通。

    detail には「何が失われるか」だけをタブごとに書く。
    """
    ret = QMessageBox.question(
        parent, title,
        f"選択した{count}件を削除します。\n\n"
        f"{detail}\n"
        "（このすぐ後であれば「削除を元に戻す」ボタンで復元できます）\n\n"
        "削除しますか？",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return ret == QMessageBox.StandardButton.Yes


class UndoSlot:
    """直近1回分の削除だけを取り消せるようにするための小さな入れ物。

    3タブとも「消したものを覚えておき、ボタンを有効化し、戻したら忘れてボタンを無効化する」
    という同じ扱いをしていたので、その手順をここにまとめている。
    何を覚えるか（リスト／辞書）は呼び出し側の自由。
    """

    def __init__(self, button=None):
        self._payload = None
        self.button = button
        if button is not None:
            button.setEnabled(False)

    def store(self, payload):
        """削除したものを記録し、Undoボタンを押せるようにする。"""
        self._payload = payload
        if self.button is not None:
            self.button.setEnabled(True)

    def take(self):
        """記録を取り出して忘れる（Undoボタンも無効に戻す）。何も無ければNone。"""
        payload = self._payload
        self._payload = None
        if self.button is not None:
            self.button.setEnabled(False)
        return payload

    def has_payload(self):
        return self._payload is not None
