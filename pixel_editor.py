"""
ドット絵エディタの共通部品。

【なぜこのモジュールがあるか】
ドット絵の編集は2箇所で使われている:
  - GUIアイコン編集タブ … タブに直接埋め込んだキャンバス（9×9固定）
  - アイテムテクスチャ編集タブ … モーダルダイアログ（画像サイズに追従）

キャンバス本体（PixelCanvas）は以前から共有していたが、周辺のUI
（ペン/バケツ/スポイトの切り替えボタン）は両者で別々に書かれていた。
また PixelEditDialog は item_texture_editor.py の中にあり、
gui_icon_editor.py を import している（＝タブ同士が依存し合っている）状態だった。

ここに集約することで、キャンバス・ツール選択・編集ダイアログが1箇所にまとまり、
タブ側のファイルは「そのタブ固有の処理」だけになる。

Copyright (c) 2026 旬茶
Licensed under the MIT License.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLabel,
    QDialog, QColorDialog, QGroupBox, QCheckBox
)
from PyQt6.QtGui import QPainter, QColor, QPen, QImage, QPixmap
from PyQt6.QtCore import Qt, QRect, pyqtSignal

from PIL import Image

DEFAULT_CANVAS_SIZE = 9   # 体力・満腹度アイコンの実寸(px)
DEFAULT_CELL_PX = 34      # 編集キャンバス上での1ピクセルあたりの表示サイズ

# ドット絵エディタ（ダイアログ）のキャンバス表示サイズの目安(px)。
# 実際のセルサイズは PIXEL_EDITOR_DISPLAY_TARGET // 画像サイズ で決める。
PIXEL_EDITOR_DISPLAY_TARGET = 420

# ツールの内部キーと表示名。左クリック=描画／右クリック=消去はキャンバス側の共通仕様。
TOOLS = (
    ("pen", "ペン"),
    ("bucket", "バケツ（塗りつぶし）"),
    ("eyedropper", "スポイト"),
)


class ToolSelector(QWidget):
    """ペン／バケツ／スポイトの切り替えボタン列。選ばれたツールのキーを tool_changed で流す。

    GUIアイコン編集タブは縦並び（QGroupBoxの中）、アイテムのダイアログは横並びで使う。
    """

    tool_changed = pyqtSignal(str)

    def __init__(self, horizontal=False, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self) if horizontal else QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.buttons = {}
        for key, label in TOOLS:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.clicked.connect(lambda _checked, k=key: self.tool_changed.emit(k))
            layout.addWidget(btn)
            self.buttons[key] = btn
        self.buttons["pen"].setChecked(True)

    def select(self, key):
        """指定ツールを選択状態にする（シグナルは出さない）。"""
        for k, btn in self.buttons.items():
            btn.setChecked(k == key)

    def current_tool(self):
        for key, btn in self.buttons.items():
            if btn.isChecked():
                return key
        return "pen"


class CompactColorPicker(QWidget):
    """省スペースな色選択ウィジェット。

    以前はQColorDialogを丸ごと埋め込んでいたが、あの巨大な内部レイアウト
    （色の輪・Basic/Custom colorsのグリッド・HSV/RGBのスピンボックス等）が
    そのままGUIアイコン編集タブ右列全体の最小幅を押し上げてしまい、
    ウィンドウを小さく縮められない原因になっていた。

    ここでは「よく使う色のプリセットスウォッチ」＋「現在の色」＋
    「他の色を選ぶ...（モーダルのQColorDialogをその場だけ開く）」という
    最小限の常時表示に絞り、細かい調整（アルファ値・スクリーンから拾う等）は
    必要な時だけモーダルで開く方式にして、幅を大きく減らしている。
    """

    currentColorChanged = pyqtSignal(QColor)

    PRESET_COLORS = (
        "#000000", "#5a5a5a", "#a5a5a5", "#ffffff",
        "#dc2828", "#e67e22", "#f1c40f", "#2ecc71",
        "#16a085", "#3498db", "#2c3e50", "#9b59b6",
        "#e91e63", "#8d5524", "#ecf0f1", "#7f8c8d",
    )
    SWATCH_PX = 20
    COLUMNS = 8

    def __init__(self, initial=None, parent=None):
        super().__init__(parent)
        self._color = QColor(initial) if initial is not None else QColor(220, 40, 40, 255)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        grid = QGridLayout()
        grid.setSpacing(3)
        for i, hex_code in enumerate(self.PRESET_COLORS):
            btn = QPushButton()
            btn.setFixedSize(self.SWATCH_PX, self.SWATCH_PX)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(hex_code)
            # 白系の色も背景に埋もれないよう、枠線を付けて視認性を上げる。
            btn.setStyleSheet(
                f"QPushButton {{ background-color: {hex_code}; border: 1px solid #444444; "
                "border-radius: 3px; }"
                "QPushButton:hover { border: 1px solid #2f77d8; }"
            )
            btn.clicked.connect(lambda _checked, c=hex_code: self.set_current_color(QColor(c)))
            grid.addWidget(btn, i // self.COLUMNS, i % self.COLUMNS)
        layout.addLayout(grid)

        current_row = QHBoxLayout()
        self.current_swatch = QPushButton()
        self.current_swatch.setFixedSize(40, 26)
        self.current_swatch.setCursor(Qt.CursorShape.PointingHandCursor)
        self.current_swatch.setToolTip("クリックで他の色を選ぶ（アルファ値・スクリーンからの色拾いも可）")
        self.current_swatch.clicked.connect(self._open_full_dialog)
        current_row.addWidget(self.current_swatch)

        self.hex_label = QLabel()
        self.hex_label.setStyleSheet("font-size: 11px; color: #666;")
        current_row.addWidget(self.hex_label)
        current_row.addStretch(1)
        layout.addLayout(current_row)

        self.other_btn = QPushButton("他の色を選ぶ...")
        self.other_btn.clicked.connect(self._open_full_dialog)
        layout.addWidget(self.other_btn)

        self._refresh_swatch()

    def _open_full_dialog(self):
        chosen = QColorDialog.getColor(
            self._color, self, "色を選ぶ",
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if chosen.isValid():
            self.set_current_color(chosen)

    def _refresh_swatch(self):
        r, g, b, a = self._color.red(), self._color.green(), self._color.blue(), self._color.alpha()
        self.current_swatch.setStyleSheet(
            f"QPushButton {{ background-color: rgba({r},{g},{b},{a}); "
            "border: 1px solid #444444; border-radius: 3px; }"
        )
        self.hex_label.setText(self._color.name(QColor.NameFormat.HexArgb))

    def current_color(self):
        return QColor(self._color)

    def set_current_color(self, color, emit=True):
        self._color = QColor(color)
        self._refresh_swatch()
        if emit:
            self.currentColorChanged.emit(QColor(self._color))


class PixelCanvas(QWidget):
    """9x9（既定）のドット絵編集キャンバス。透過はチェッカーボードで表示する。"""

    changed = pyqtSignal()
    color_picked = pyqtSignal(tuple)

    def __init__(self, size=DEFAULT_CANVAS_SIZE, cell_px=DEFAULT_CELL_PX):
        super().__init__()
        self.size_px = size
        self.cell_px = cell_px
        self.setFixedSize(size * cell_px, size * cell_px)
        self.pixels = [[None] * size for _ in range(size)]  # None=透明 / (r,g,b,a)
        self.current_color = (0, 0, 0, 255)
        self.tool = "pen"  # pen / eraser / bucket / eyedropper
        self.setMouseTracking(True)
        self._undo_stack = []
        self._undo_limit = 30
        self._onion_skin = None  # 下敷き表示用の参照画像(PIL.Image, RGBA) or None

    def set_tool(self, tool: str):
        self.tool = tool

    def set_onion_skin(self, image):
        """
        下敷き（オニオンスキン）として薄く表示する参照画像を設定する。
        image: PIL.Image (RGBA) または None（非表示）。
        """
        if image is None:
            self._onion_skin = None
        else:
            img = image.convert("RGBA")
            if img.size != (self.size_px, self.size_px):
                img = img.resize((self.size_px, self.size_px), Image.NEAREST)
            self._onion_skin = img
        self.update()

    def set_color(self, rgba):
        self.current_color = rgba

    # ---- 取り消し（Undo） ----
    def _snapshot(self):
        return [row[:] for row in self.pixels]

    def _push_undo(self):
        self._undo_stack.append(self._snapshot())
        if len(self._undo_stack) > self._undo_limit:
            self._undo_stack.pop(0)

    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0

    def undo(self):
        if not self._undo_stack:
            return
        self.pixels = self._undo_stack.pop()
        self.update()
        self.changed.emit()

    def push_undo_snapshot(self, snapshot):
        """
        彩度調整のように、キャンバス外から一括で pixels を書き換える操作のために、
        変更前の状態を外から明示的にUndo履歴へ積めるようにする。
        """
        self._undo_stack.append(snapshot)
        if len(self._undo_stack) > self._undo_limit:
            self._undo_stack.pop(0)

    def reset_undo_history(self):
        """バリアント切り替えなど、別の絵に切り替わったタイミングで呼ぶ。"""
        self._undo_stack = []

    def clear(self):
        self._push_undo()
        self.pixels = [[None] * self.size_px for _ in range(self.size_px)]
        self.update()
        self.changed.emit()

    def is_empty(self) -> bool:
        return all(p is None for row in self.pixels for p in row)

    def load_image(self, img: Image.Image):
        img = img.convert("RGBA")
        if img.size != (self.size_px, self.size_px):
            img = img.resize((self.size_px, self.size_px), Image.NEAREST)
        for y in range(self.size_px):
            for x in range(self.size_px):
                r, g, b, a = img.getpixel((x, y))
                self.pixels[y][x] = None if a == 0 else (r, g, b, a)
        self.reset_undo_history()
        self.update()
        self.changed.emit()

    def to_image(self) -> Image.Image:
        img = Image.new("RGBA", (self.size_px, self.size_px), (0, 0, 0, 0))
        for y in range(self.size_px):
            for x in range(self.size_px):
                if self.pixels[y][x]:
                    img.putpixel((x, y), self.pixels[y][x])
        return img

    def shift(self, dx: int, dy: int):
        """
        絵全体を (dx, dy) ドットだけずらす。
        dx>0で右、dx<0で左、dy>0で下、dy<0で上に1ドット移動。
        画面外にはみ出た部分は失われ、反対側の列/行は透明になる。
        """
        self._push_undo()
        new_pixels = [[None] * self.size_px for _ in range(self.size_px)]
        for y in range(self.size_px):
            for x in range(self.size_px):
                src_x, src_y = x - dx, y - dy
                if 0 <= src_x < self.size_px and 0 <= src_y < self.size_px:
                    new_pixels[y][x] = self.pixels[src_y][src_x]
        self.pixels = new_pixels
        self.update()
        self.changed.emit()

    # ---- 描画 ----
    def paintEvent(self, event):
        painter = QPainter(self)
        half = max(1, self.cell_px // 2)
        onion = self._onion_skin
        for y in range(self.size_px):
            for x in range(self.size_px):
                px = self.pixels[y][x]
                left = x * self.cell_px
                top = y * self.cell_px
                if px is None:
                    # 透明マスは、1ドットの中を白×薄いグレーの2x2市松模様に塗って
                    # 「ここは透明」だと一目でわかるようにする（どのマスも同じ模様）
                    painter.fillRect(QRect(left, top, half, half), QColor(235, 235, 235))
                    painter.fillRect(
                        QRect(left + half, top, self.cell_px - half, half), QColor(255, 255, 255)
                    )
                    painter.fillRect(
                        QRect(left, top + half, half, self.cell_px - half), QColor(255, 255, 255)
                    )
                    painter.fillRect(
                        QRect(left + half, top + half, self.cell_px - half, self.cell_px - half),
                        QColor(235, 235, 235),
                    )
                    # オニオンスキン（下敷き）が設定されていれば、透明マスの上に薄く重ねて表示する。
                    # 自分で描いた不透明なドットは上のelse分岐で完全に塗りつぶすので、
                    # まだ描いていない部分だけに「なぞる目安」として見える。
                    if onion is not None:
                        orr, org, orb, ora = onion.getpixel((x, y))
                        if ora > 0:
                            overlay_alpha = int(ora * 0.45)
                            painter.fillRect(
                                QRect(left, top, self.cell_px, self.cell_px),
                                QColor(orr, org, orb, overlay_alpha),
                            )
                else:
                    r, g, b, a = px
                    painter.fillRect(QRect(left, top, self.cell_px, self.cell_px), QColor(r, g, b, a))
        painter.setPen(QPen(QColor(70, 70, 70), 1))
        for i in range(self.size_px + 1):
            painter.drawLine(0, i * self.cell_px, self.size_px * self.cell_px, i * self.cell_px)
            painter.drawLine(i * self.cell_px, 0, i * self.cell_px, self.size_px * self.cell_px)

    # ---- 入力 ----
    def _cell_at(self, pos):
        x = pos.x() // self.cell_px
        y = pos.y() // self.cell_px
        if 0 <= x < self.size_px and 0 <= y < self.size_px:
            return int(x), int(y)
        return None

    def mousePressEvent(self, event):
        self._push_undo()
        self._handle(event, event.button())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._handle(event, Qt.MouseButton.LeftButton)
        elif event.buttons() & Qt.MouseButton.RightButton:
            self._handle(event, Qt.MouseButton.RightButton)

    def contextMenuEvent(self, event):
        # 右クリックで標準のコンテキストメニューが出ないようにする
        event.accept()

    def _handle(self, event, button):
        cell = self._cell_at(event.position().toPoint())
        if not cell:
            return
        x, y = cell

        if self.tool == "pen":
            if button == Qt.MouseButton.LeftButton:
                self.pixels[y][x] = self.current_color
            elif button == Qt.MouseButton.RightButton:
                self.pixels[y][x] = None
        elif self.tool == "eyedropper":
            if button == Qt.MouseButton.LeftButton and self.pixels[y][x]:
                self.current_color = self.pixels[y][x]
                self.color_picked.emit(self.current_color)
        elif self.tool == "bucket":
            if button == Qt.MouseButton.LeftButton:
                self._flood_fill(x, y, self.current_color)
            elif button == Qt.MouseButton.RightButton:
                self._flood_fill(x, y, None)
        self.update()
        self.changed.emit()

    def _flood_fill(self, x, y, replacement):
        target = self.pixels[y][x]
        if target == replacement:
            return
        stack = [(x, y)]
        seen = set()
        while stack:
            cx, cy = stack.pop()
            if (cx, cy) in seen:
                continue
            if not (0 <= cx < self.size_px and 0 <= cy < self.size_px):
                continue
            if self.pixels[cy][cx] != target:
                continue
            self.pixels[cy][cx] = replacement
            seen.add((cx, cy))
            stack.extend([(cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)])


class PixelEditDialog(QDialog):
    """
    アイテムテクスチャ用のドット絵エディタ（モーダルダイアログ）。
    - ゼロから描く：original_image=None、または「オリジナルから読み込み直す」を使わない
    - 取り込んだ外部PNGの仕上げ・手直し：initial_image に既存のcustom_imageを渡す
    GUIアイコン編集で使っているPixelCanvasをそのまま再利用している。
    """

    def __init__(self, parent, size: int, initial_image=None, original_image=None,
                 title="", post_process=None):
        super().__init__(parent)
        self.setWindowTitle(f"ドット絵エディタ {title}".strip())
        self.result_image = None  # 「保存して閉じる」を押した場合にのみセットされる
        self._original_image = original_image
        # 保存時に画像へかける後処理（アイテムでは輪郭の半透明ピクセルの二値化）。
        # エディタ自体を用途に依存させないため、呼び出し側から渡してもらう。
        self._post_process = post_process

        layout = QVBoxLayout(self)

        info = QLabel(f"作業解像度: {size}×{size}px（このアイテムの画像サイズに合わせています）")
        info.setStyleSheet("font-size: 11px; color: #666;")
        layout.addWidget(info)

        # ---- ツール ----
        self.tool_selector = ToolSelector(horizontal=True)
        self.tool_selector.tool_changed.connect(self._select_tool)
        self.tool_buttons = self.tool_selector.buttons  # 既存コードとの互換
        layout.addWidget(self.tool_selector)

        tip = QLabel("左クリック＝描画／右クリック＝消去（ペン・バケツ共通）")
        tip.setStyleSheet("font-size: 11px; color: #666;")
        layout.addWidget(tip)

        # ---- オニオンスキン ----
        # GUIアイコン編集タブと同じ「透明な部分に元の絵を薄く重ねて表示」機能。
        # アイテムでは「元画像」＝original_image（外部PNG差し替え前のオリジナル）を下敷きにする。
        self.onion_skin_checkbox = QCheckBox("オニオンスキン表示（透明な部分に、下敷きの絵を薄く重ねて表示）")
        self.onion_skin_checkbox.setToolTip(
            "オリジナルの絵を薄く下敷き表示します。自分で描いた部分はそのまま見え、\n"
            "まだ描いていない透明な部分だけになぞる目安が出ます。"
        )
        self.onion_skin_checkbox.setEnabled(self._original_image is not None)
        if self._original_image is None:
            self.onion_skin_checkbox.setToolTip("オリジナルの絵が無いため使用できません。")
        self.onion_skin_checkbox.stateChanged.connect(lambda _s: self._update_onion_skin())
        layout.addWidget(self.onion_skin_checkbox)

        # ---- キャンバス ----
        cell_px = max(2, PIXEL_EDITOR_DISPLAY_TARGET // size)
        self.canvas = PixelCanvas(size=size, cell_px=cell_px)
        self.canvas.set_color((220, 40, 40, 255))
        self.canvas.color_picked.connect(self._on_color_picked)
        self.canvas.changed.connect(self._update_edit_preview)
        canvas_row = QHBoxLayout()
        canvas_row.addStretch(1)
        canvas_row.addWidget(self.canvas)
        canvas_row.addStretch(1)
        layout.addLayout(canvas_row)

        if initial_image is not None:
            img = initial_image.convert("RGBA")
            if img.size != (size, size):
                img = img.resize((size, size), Image.NEAREST)
            self.canvas.load_image(img)

        # ---- 編集中プレビュー（実寸に近いサイズ） ----
        # GUIアイコン編集タブと同じく、拡大表示しているキャンバスとは別に、
        # 実際の見え方に近い縮尺のプレビューを常に確認できるようにする。
        preview_row = QHBoxLayout()
        preview_col = QVBoxLayout()
        preview_label = QLabel("編集中プレビュー（実寸に近いサイズ）")
        preview_label.setWordWrap(True)
        preview_label.setFixedWidth(108)
        preview_col.addWidget(preview_label)
        self.edit_preview = QLabel("（空）")
        self.edit_preview.setFixedSize(108, 108)
        self.edit_preview.setStyleSheet(
            "background: repeating-conic-gradient(#ccc 0% 25%, #999 0% 50%) 50% / 12px 12px;"
            "border: 1px solid #2f77d8; color: #888;"
        )
        self.edit_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_col.addWidget(self.edit_preview, alignment=Qt.AlignmentFlag.AlignTop)
        preview_row.addLayout(preview_col)
        preview_row.addStretch(1)
        layout.addLayout(preview_row)

        # ---- 色選択 ----
        # GUIアイコン編集タブと同じCompactColorPicker（よく使う色のスウォッチ＋
        # 現在の色＋「他の色を選ぶ...」）に統一。以前は「色を選ぶ...」ボタン1つで
        # 毎回モーダルのQColorDialogを開く必要があったが、頻用色はワンクリックで選べる。
        color_group = QGroupBox("色")
        color_layout = QVBoxLayout(color_group)
        self.color_picker = CompactColorPicker(QColor(220, 40, 40, 255))
        self.color_picker.currentColorChanged.connect(self._on_color_changed)
        color_layout.addWidget(self.color_picker)
        layout.addWidget(color_group)

        # ---- 元に戻す系ボタン ----
        reset_row = QHBoxLayout()
        if self._original_image is not None:
            reset_orig_btn = QPushButton("オリジナルの絵から読み込み直す")
            reset_orig_btn.clicked.connect(self._on_load_original)
            reset_row.addWidget(reset_orig_btn)
        clear_btn = QPushButton("全消去")
        clear_btn.clicked.connect(self.canvas.clear)
        reset_row.addWidget(clear_btn)
        layout.addLayout(reset_row)

        self._update_edit_preview()

        # ---- 保存/キャンセル ----
        btn_row = QHBoxLayout()
        save_btn = QPushButton("保存して閉じる")
        save_btn.setStyleSheet("font-weight: bold;")
        save_btn.clicked.connect(self._on_save)
        cancel_btn = QPushButton("キャンセル")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _select_tool(self, key):
        self.tool_selector.select(key)
        self.canvas.set_tool(key)

    def _on_color_changed(self, color: QColor):
        self.canvas.set_color((color.red(), color.green(), color.blue(), color.alpha()))

    def _on_color_picked(self, rgba):
        r, g, b, a = rgba
        self.color_picker.set_current_color(QColor(r, g, b, a), emit=False)
        self.canvas.set_color(rgba)

    def _on_load_original(self):
        if self._original_image is None:
            return
        size = self.canvas.size_px
        img = self._original_image.convert("RGBA")
        if img.size != (size, size):
            img = img.resize((size, size), Image.NEAREST)
        self.canvas.load_image(img)
        self._update_onion_skin()

    def _update_onion_skin(self):
        """オニオンスキン表示チェックボックスの状態に応じて、下敷き画像を更新する。"""
        if not self.onion_skin_checkbox.isChecked() or self._original_image is None:
            self.canvas.set_onion_skin(None)
            return
        self.canvas.set_onion_skin(self._original_image)

    def _update_edit_preview(self):
        if self.canvas.is_empty():
            # setPixmap(空のQPixmap)を後から呼ぶと、QLabelの仕様でテキストまで
            # 消えてしまう（pixmapが設定されている扱いになるため）。
            # 先にpixmapを空にしてから、最後にsetTextすることで文字を確実に出す。
            self.edit_preview.setPixmap(QPixmap())
            self.edit_preview.setText("（空）")
            return
        img = self.canvas.to_image()
        qimg = QImage(img.tobytes("raw", "RGBA"), img.width, img.height, QImage.Format.Format_RGBA8888)
        pixmap = QPixmap.fromImage(qimg).scaled(
            108, 108, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation
        )
        self.edit_preview.setPixmap(pixmap)
        self.edit_preview.setText("")

    def _on_save(self):
        img = self.canvas.to_image()
        self.result_image = self._post_process(img) if self._post_process else img
        self.accept()
