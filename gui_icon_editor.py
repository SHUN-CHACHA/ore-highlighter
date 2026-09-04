"""
GUI要素（体力ゲージ・満腹度ゲージ）用のドット絵エディタ。

重要な設計メモ（当初仕様書からの修正点）:
- 体力・満腹度アイコンは16x16ではなく実際は9x9ピクセル。
- Minecraft 1.20.2以降、assets/minecraft/textures/gui/sprites/hud/ 以下に
  状態ごとの「個別の静止画」として分割されている（.mcmetaによるコマ送りアニメーションではない）。
  例: full.png, half.png, poisoned_full.png, hardcore_full_blinking.png ...
- そのため本エディタは「アニメーションフレーム管理」ではなく「状態(バリアント)管理」として作る。
  ユーザーは決まったバリアント名の一覧から1つずつ選び、ドット絵を描く/インポートする。
- food（満腹度）側の正確なサブフォルダ構成は未検証。FOOD_SUBDIR定数を変えれば調整できる。
  実際にjarを展開して assets/minecraft/textures/gui/sprites/hud/ の中を確認し、
  ズレていたら HEART_SUBDIR / FOOD_SUBDIR を修正してください。

Copyright (c) 2026 旬茶
Licensed under the MIT License. 詳細は同梱の LICENSE ファイルを参照してください。
"""

import os
import json
import zipfile
import tempfile
import colorsys
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QFileDialog, QMessageBox, QGroupBox, QMenu,
    QLineEdit, QCheckBox, QAbstractItemView, QSlider, QScrollArea, QFrame
)
from PyQt6.QtGui import QColor, QPixmap, QImage, QShortcut, QKeySequence
from PyQt6.QtCore import Qt
from PIL import Image

from ui_utils import fix_button_widths
import pack_backup
import list_ui
# ドット絵キャンバスとツール選択は、アイテムテクスチャ編集タブと共通の部品。
# （PixelCanvas は以前このファイルにあり、item_texture_editor が import していた）
from pixel_editor import PixelCanvas, ToolSelector, CompactColorPicker  # noqa: F401  （PixelCanvasは再輸出）

CANVAS_SIZE = 9   # 実際のアイコンサイズ(px)
CELL_PX = 34      # 編集キャンバス上での1ピクセルあたりの表示サイズ

HEART_SUBDIR = "heart"
FOOD_SUBDIR = ""  # 確認済み：foodは専用フォルダを持たず、hud直下に置かれる

HEART_VARIANTS = [
    "full", "full_blinking", "half", "half_blinking",
    "hardcore_full", "hardcore_full_blinking", "hardcore_half", "hardcore_half_blinking",
    "poisoned_full", "poisoned_full_blinking", "poisoned_half", "poisoned_half_blinking",
    "poisoned_hardcore_full", "poisoned_hardcore_full_blinking",
    "poisoned_hardcore_half", "poisoned_hardcore_half_blinking",
    "withered_full", "withered_full_blinking", "withered_half", "withered_half_blinking",
    "withered_hardcore_full", "withered_hardcore_full_blinking",
    "withered_hardcore_half", "withered_hardcore_half_blinking",
    "frozen_full", "frozen_full_blinking", "frozen_half", "frozen_half_blinking",
    "frozen_hardcore_full", "frozen_hardcore_full_blinking",
    "frozen_hardcore_half", "frozen_hardcore_half_blinking",
    "absorbing_full", "absorbing_full_blinking", "absorbing_half", "absorbing_half_blinking",
    "absorbing_hardcore_full", "absorbing_hardcore_full_blinking",
    "absorbing_hardcore_half", "absorbing_hardcore_half_blinking",
    "container", "container_blinking", "container_hardcore", "container_hardcore_blinking",
    "vehicle_container", "vehicle_full", "vehicle_half",
]

FOOD_VARIANTS = [
    "food_empty", "food_half", "food_full",
    "food_empty_hunger", "food_half_hunger", "food_full_hunger",
]

# バリアント名 -> 日本語見出し（一覧・編集中ラベルに表示するための説明）
VARIANT_LABELS_JA = {
    # 体力（heart）
    "full": "満タン",
    "full_blinking": "満タン（点滅）",
    "half": "半分",
    "half_blinking": "半分（点滅）",
    "hardcore_full": "ハードコア・満タン",
    "hardcore_full_blinking": "ハードコア・満タン（点滅）",
    "hardcore_half": "ハードコア・半分",
    "hardcore_half_blinking": "ハードコア・半分（点滅）",
    "poisoned_full": "毒状態・満タン",
    "poisoned_full_blinking": "毒状態・満タン（点滅）",
    "poisoned_half": "毒状態・半分",
    "poisoned_half_blinking": "毒状態・半分（点滅）",
    "poisoned_hardcore_full": "毒状態×ハードコア・満タン",
    "poisoned_hardcore_full_blinking": "毒状態×ハードコア・満タン（点滅）",
    "poisoned_hardcore_half": "毒状態×ハードコア・半分",
    "poisoned_hardcore_half_blinking": "毒状態×ハードコア・半分（点滅）",
    "withered_full": "衰弱状態・満タン",
    "withered_full_blinking": "衰弱状態・満タン（点滅）",
    "withered_half": "衰弱状態・半分",
    "withered_half_blinking": "衰弱状態・半分（点滅）",
    "withered_hardcore_full": "衰弱状態×ハードコア・満タン",
    "withered_hardcore_full_blinking": "衰弱状態×ハードコア・満タン（点滅）",
    "withered_hardcore_half": "衰弱状態×ハードコア・半分",
    "withered_hardcore_half_blinking": "衰弱状態×ハードコア・半分（点滅）",
    "frozen_full": "凍結状態・満タン",
    "frozen_full_blinking": "凍結状態・満タン（点滅）",
    "frozen_half": "凍結状態・半分",
    "frozen_half_blinking": "凍結状態・半分（点滅）",
    "frozen_hardcore_full": "凍結状態×ハードコア・満タン",
    "frozen_hardcore_full_blinking": "凍結状態×ハードコア・満タン（点滅）",
    "frozen_hardcore_half": "凍結状態×ハードコア・半分",
    "frozen_hardcore_half_blinking": "凍結状態×ハードコア・半分（点滅）",
    "absorbing_full": "吸収ハート・満タン",
    "absorbing_full_blinking": "吸収ハート・満タン（点滅）",
    "absorbing_half": "吸収ハート・半分",
    "absorbing_half_blinking": "吸収ハート・半分（点滅）",
    "absorbing_hardcore_full": "吸収ハート×ハードコア・満タン",
    "absorbing_hardcore_full_blinking": "吸収ハート×ハードコア・満タン（点滅）",
    "absorbing_hardcore_half": "吸収ハート×ハードコア・半分",
    "absorbing_hardcore_half_blinking": "吸収ハート×ハードコア・半分（点滅）",
    "container": "空枠（背景）",
    "container_blinking": "空枠（背景・点滅）",
    "container_hardcore": "ハードコア空枠（背景）",
    "container_hardcore_blinking": "ハードコア空枠（背景・点滅）",
    "vehicle_container": "乗り物用・空枠",
    "vehicle_full": "乗り物用・満タン",
    "vehicle_half": "乗り物用・半分",
    # 満腹度（food）
    "food_empty": "満腹度・空",
    "food_half": "満腹度・半分",
    "food_full": "満腹度・満タン",
    "food_empty_hunger": "満腹度・空（空腹エフェクト時）",
    "food_half_hunger": "満腹度・半分（空腹エフェクト時）",
    "food_full_hunger": "満腹度・満タン（空腹エフェクト時）",
}


def apply_saturation_delta_to_image(img: Image.Image, delta: float) -> Image.Image:
    """
    PIL.Image (RGBA) 全体に、彩度調整スライダーと同じ変換を適用して新しい画像を返す。
    delta < 0: 白を混ぜて薄くする（ティント）／ delta > 0: HSVの彩度を上げる（鮮やかに）
    複数バリアントへの一括適用（保存済みの絵に直接効かせる場合）で使う。
    """
    img = img.convert("RGBA")
    out = Image.new("RGBA", img.size)
    src = img.load()
    dst = out.load()
    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = src[x, y]
            if a == 0:
                dst[x, y] = (0, 0, 0, 0)
                continue
            if delta < 0:
                factor = -delta
                nr = r + (255 - r) * factor
                ng = g + (255 - g) * factor
                nb = b + (255 - b) * factor
                dst[x, y] = (int(round(nr)), int(round(ng)), int(round(nb)), a)
            elif delta > 0:
                h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
                s = max(0.0, min(1.0, s + delta))
                nr, ng, nb = colorsys.hsv_to_rgb(h, s, v)
                dst[x, y] = (int(round(nr * 255)), int(round(ng * 255)), int(round(nb * 255)), a)
            else:
                dst[x, y] = (r, g, b, a)
    return out


class GuiIconEditorTab(QWidget):
    """体力・満腹度アイコンのバリアント一覧＋編集キャンバスをまとめたタブ。"""

    def __init__(self):
        super().__init__()
        # variant_name -> PIL.Image (RGBA) or None(未着手)
        self.icons = {}
        self._current_variant = None
        self._dirty = False  # 「保存する」を押していない編集があるか
        self.reference_dir = None  # jarから展開した .../gui/sprites/hud フォルダ
        self._duplicate_source = None       # 右クリックで「複製元にする」を選んだ画像(PIL.Image)
        self._duplicate_source_name = None  # その複製元のバリアント名(表示用)
        self._saturation_snapshot = None    # 彩度調整スライダーをドラッグ中の、操作前の状態（単一選択時）
        self._saturation_batch_snapshot = None  # 同上（複数選択・保存済みの絵に直接適用する場合）
        self._last_batch_tint_snapshot = None   # 「一括適用を元に戻す」用の直近1回分の記録
        # main.py側の出力設定(パック名, 出力先フォルダ)を取得するためのコールバック。
        # main.py側で `gui_icon_tab.get_pack_output_info = lambda: (name, dir)` の形で注入される。
        self.get_pack_output_info = None
        # main.py側で直近テクスチャを読み込んだ場所のヒントを取得するコールバック。
        # 「既存パックから読み込む」ダイアログの初期位置に使う。
        self.get_source_dir_hint = None
        # main.py側で直近「既存のOreHighlighterプロジェクトを開く」に使った場所の
        # ヒントを取得するコールバック。設定されていれば、こちらを優先して
        # 「既存パックから読み込む」ダイアログの初期位置に使う（同じパックを
        # 開いた直後なら、フォルダ探しをやり直さずに済むように）。
        self.get_project_dir_hint = None
        # 「読み込み」タブへ状態表示をミラーするためのフック（SourceImportTabが注入する）。
        self.report_source_status = lambda text: None
        # 「読み込み」タブに並べるボタン群。_build_ui() より前に作っておく
        # （_do_backup_export() 等が self.open_backup_folder_btn を参照するため）。
        self.build_source_widgets()
        self._build_ui()
        self._reload_variant_list()
        self._update_dirty_indicator()

    def build_source_widgets(self):
        """
        「読み込み」タブ（source_tab.SourceImportTab）に並べるウィジェットを作る。

        ブロックエフェクトタブの build_source_widgets() と同じ方針で、ウィジェットの
        所有者とシグナル接続はこのクラスのまま、並べる場所だけを新タブに移している。
        レイアウトに追加されるまでは親なしウィジェットなので、SourceImportTab を
        作らずに GuiIconEditorTab 単体を生成しても壊れない（テスト等）。
        """
        self.ref_dir_btn = QPushButton("参照元フォルダを開く...")
        self.ref_dir_btn.setToolTip(
            "jarを使わずフォルダを直接開いた場合、hud フォルダ（heart/food の親）を指定してください"
        )
        self.ref_dir_btn.clicked.connect(self._on_choose_reference_dir)

        self.import_pack_label = QLabel("既存のリソースパックから体力・満腹度アイコンを読み込む")
        self.import_pack_label.setStyleSheet("font-size: 11px; color: #666;")
        self.import_pack_label.setWordWrap(True)

        self.import_pack_folder_btn = QPushButton("フォルダから読み込む...")
        self.import_pack_folder_btn.setToolTip(
            "展開済みのリソースパック（pack.mcmetaがあるフォルダ）を選んでください"
        )
        self.import_pack_folder_btn.clicked.connect(self._on_import_pack_folder)

        self.import_pack_zip_btn = QPushButton("zipから読み込む...")
        self.import_pack_zip_btn.setToolTip("zip化されたリソースパックファイルを選んでください")
        self.import_pack_zip_btn.clicked.connect(self._on_import_pack_zip)

        self.open_backup_folder_btn = QPushButton("保存先フォルダを開く")
        self.open_backup_folder_btn.setVisible(False)
        self.open_backup_folder_btn.clicked.connect(self._on_open_backup_folder)

    def _set_import_status(self, text):
        """GUIアイコンタブの状態表示を更新し、同じ文言を「読み込み」タブにも出す。"""
        self.import_status_label.setText(text)
        self.report_source_status(text)

    def _build_ui(self):
        # 以前はQColorDialogを丸ごと埋め込んでおり、その巨大な最小サイズが
        # ウィンドウ全体（タブ切り替え全体）に伝播してしまう問題があった。
        # 色パネルはCompactColorPickerに置き換えて根本的に小さくしたが、
        # 念のためタブの最小サイズをウィンドウから切り離すQScrollAreaは維持する。
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)
        content = QWidget()
        scroll.setWidget(content)

        root = QHBoxLayout(content)

        # ---- 左: バリアント一覧 ----
        left = QVBoxLayout()
        left.addWidget(QLabel("状態（バリアント）一覧　※編集済みには●が付く／右クリックで複製メニュー"))

        dnd_badge = QLabel("📥 D&D対応：PNG / フォルダ / zip")
        dnd_badge.setStyleSheet(
            "background: #2f77d8; color: white; font-size: 10px; font-weight: bold;"
            "border-radius: 8px; padding: 2px 8px;"
        )
        dnd_row = QHBoxLayout()
        dnd_row.addWidget(dnd_badge)
        dnd_row.addStretch(1)
        left.addLayout(dnd_row)

        self.variant_progress_label = QLabel("編集済み: 0/55")
        self.variant_progress_label.setStyleSheet("font-size: 11px; color: #2f77d8; font-weight: bold;")
        left.addWidget(self.variant_progress_label)

        self.variant_search_box = QLineEdit()
        self.variant_search_box.setPlaceholderText("状態名で絞り込み（例: 満タン、full）")
        self.variant_search_box.textChanged.connect(self._reload_variant_list)
        left.addWidget(self.variant_search_box)

        # 「編集済みのみ／未編集のみ」の排他チェックボックスは3タブ共通の部品。
        self.variant_filter = list_ui.EditedFilterBox()
        self.variant_filter.changed.connect(self._reload_variant_list)
        self.edited_only_checkbox = self.variant_filter.edited_only_checkbox
        self.unedited_only_checkbox = self.variant_filter.unedited_only_checkbox
        left.addWidget(self.variant_filter)

        self.variant_list = QListWidget()
        self.variant_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.variant_list.currentItemChanged.connect(self._on_variant_selected)
        self.variant_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.variant_list.customContextMenuRequested.connect(self._on_variant_list_context_menu)
        left.addWidget(self.variant_list)

        self.duplicate_status_label = QLabel("複製元: 未設定")
        self.duplicate_status_label.setStyleSheet("font-size: 11px; color: #666;")
        left.addWidget(self.duplicate_status_label)

        dup_row = QHBoxLayout()
        clear_btn = QPushButton("選択を削除")
        clear_btn.setToolTip("選択した状態（複数可）の保存済みの絵を消去します")
        clear_btn.clicked.connect(self._on_remove_selected_variants)
        dup_row.addWidget(clear_btn)
        left.addLayout(dup_row)

        self.undo_remove_variants_btn = QPushButton("削除を元に戻す")
        self.undo_remove_variants_btn.setToolTip("直前の「選択を削除」だけを取り消せます（1回分のみ）")
        self.undo_remove_variants_btn.clicked.connect(self._on_undo_remove_variants)
        left.addWidget(self.undo_remove_variants_btn)
        # 直近1回分の削除を覚えておく共通の入れ物（ボタンの有効/無効も面倒を見る）
        self.undo_remove_variants = list_ui.UndoSlot(self.undo_remove_variants_btn)

        root.addLayout(left, 1)

        # ---- 中央: キャンバス ----
        center = QVBoxLayout()
        self.variant_label = QLabel("（左の一覧からバリアントを選んでください）")
        self.variant_label.setStyleSheet("font-weight:bold;")
        center.addWidget(self.variant_label)

        save_row = QHBoxLayout()
        self.save_btn = QPushButton("保存する")
        self.save_btn.setToolTip("編集内容をこのバリアントとして確定します")
        self.save_btn.clicked.connect(self._on_save_variant)
        self.revert_btn = QPushButton("元に戻す")
        self.revert_btn.setToolTip("保存されていない編集を破棄し、最後に保存した状態に戻します")
        self.revert_btn.clicked.connect(self._on_revert_variant)
        self.undo_btn = QPushButton("取り消し（Ctrl+Z）")
        self.undo_btn.setToolTip("直前の一手だけ取り消します（保存前の下書き段階でのやり直し用）")
        self.undo_btn.clicked.connect(self._on_undo)
        undo_shortcut = QShortcut(QKeySequence("Ctrl+Z"), self)
        undo_shortcut.activated.connect(self._on_undo)
        save_row.addWidget(self.save_btn)
        save_row.addWidget(self.revert_btn)
        save_row.addWidget(self.undo_btn)
        center.addLayout(save_row)

        copy_paste_row = QHBoxLayout()
        self.copy_btn = QPushButton("コピー")
        self.copy_btn.setToolTip("今表示している絵（保存前の下書きでもOK）を複製元としてコピーします")
        self.copy_btn.clicked.connect(self._on_copy_current)
        self.paste_btn = QPushButton("ペースト")
        self.paste_btn.setToolTip("コピーした絵を、今開いているバリアントに貼り付けます（下書き扱い、保存するまで確定しません）")
        self.paste_btn.clicked.connect(self._on_paste_current)
        self.paste_btn.setEnabled(False)
        copy_paste_row.addWidget(self.copy_btn)
        copy_paste_row.addWidget(self.paste_btn)
        center.addLayout(copy_paste_row)

        # 編集中のキャンバスを外部PNGで置き換える操作。保存・コピー等の
        # 上部ボタン群のすぐ下に置いて、「今描いているものに効く」ことを
        # 分かりやすくする。
        self.import_png_btn = QPushButton("外部PNGをインポート...")
        self.import_png_btn.setToolTip(
            f"選んだ画像を{CANVAS_SIZE}x{CANVAS_SIZE}に自動リサイズして、"
            "今選択中のバリアントに読み込みます"
        )
        self.import_png_btn.clicked.connect(self._on_import_png)
        center.addWidget(self.import_png_btn)

        self.dirty_indicator = QLabel("")
        center.addWidget(self.dirty_indicator)

        self.onion_skin_checkbox = QCheckBox("オニオンスキン表示（透明な部分に、下敷きの絵を薄く重ねて表示）")
        self.onion_skin_checkbox.setToolTip(
            "コピーした絵があればそれを、無ければオリジナル（本物）の絵を薄く下敷き表示します。\n"
            "自分で描いた部分はそのまま見え、まだ描いていない透明な部分だけになぞる目安が出ます。"
        )
        self.onion_skin_checkbox.stateChanged.connect(lambda _s: self._update_onion_skin())
        center.addWidget(self.onion_skin_checkbox)

        canvas_row = QHBoxLayout()
        self.canvas = PixelCanvas()
        self.canvas.changed.connect(self._on_canvas_changed)
        self.canvas.color_picked.connect(self._on_color_picked)
        canvas_row.addWidget(self.canvas)

        dpad_group = QGroupBox("移動（1ドットずつ）")
        dpad_grid = QGridLayout(dpad_group)
        self.move_up_btn = QPushButton("▲")
        self.move_down_btn = QPushButton("▼")
        self.move_left_btn = QPushButton("◀")
        self.move_right_btn = QPushButton("▶")
        for btn in (self.move_up_btn, self.move_down_btn, self.move_left_btn, self.move_right_btn):
            btn.setFixedSize(36, 36)
        self.move_up_btn.setToolTip("絵を上に1ドット移動")
        self.move_down_btn.setToolTip("絵を下に1ドット移動")
        self.move_left_btn.setToolTip("絵を左に1ドット移動")
        self.move_right_btn.setToolTip("絵を右に1ドット移動")
        self.move_up_btn.clicked.connect(lambda: self._shift_canvas(0, -1))
        self.move_down_btn.clicked.connect(lambda: self._shift_canvas(0, 1))
        self.move_left_btn.clicked.connect(lambda: self._shift_canvas(-1, 0))
        self.move_right_btn.clicked.connect(lambda: self._shift_canvas(1, 0))
        # 十字キー配置: 上段中央=▲、中段左右=◀▶、下段中央=▼
        dpad_grid.addWidget(self.move_up_btn, 0, 1)
        dpad_grid.addWidget(self.move_left_btn, 1, 0)
        dpad_grid.addWidget(self.move_right_btn, 1, 2)
        dpad_grid.addWidget(self.move_down_btn, 2, 1)
        canvas_row.addWidget(dpad_group, alignment=Qt.AlignmentFlag.AlignVCenter)
        canvas_row.addStretch(1)

        center.addLayout(canvas_row)

        preview_row = QHBoxLayout()

        original_col = QVBoxLayout()
        original_label = QLabel("オリジナル（本物のアイコン・参照用）")
        original_label.setWordWrap(True)
        original_label.setFixedWidth(108)
        original_col.addWidget(original_label)
        self.original_preview = QLabel("参照元なし")
        self.original_preview.setFixedSize(108, 108)
        self.original_preview.setStyleSheet(
            "background: repeating-conic-gradient(#ccc 0% 25%, #999 0% 50%) 50% / 12px 12px;"
            "border: 1px solid #555; color: #888;"
        )
        self.original_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        original_col.addWidget(self.original_preview, alignment=Qt.AlignmentFlag.AlignTop)
        preview_row.addLayout(original_col)

        edit_col = QVBoxLayout()
        edit_label = QLabel("編集中プレビュー（実寸に近いサイズ）")
        edit_label.setWordWrap(True)
        edit_label.setFixedWidth(108)
        edit_col.addWidget(edit_label)
        self.edit_preview = QLabel("（未選択）")
        self.edit_preview.setFixedSize(108, 108)
        self.edit_preview.setStyleSheet(
            "background: repeating-conic-gradient(#ccc 0% 25%, #999 0% 50%) 50% / 12px 12px;"
            "border: 1px solid #2f77d8; color: #888;"
        )
        self.edit_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        edit_col.addWidget(self.edit_preview, alignment=Qt.AlignmentFlag.AlignTop)
        preview_row.addLayout(edit_col)

        preview_row.addStretch(1)
        center.addLayout(preview_row)

        # 参照元フォルダの指定・既存リソースパックからの読み込みは、
        # 「読み込み」タブ（source_tab.SourceImportTab）に集約した。
        # ボタンの実体は build_source_widgets() で作り、新タブ側に並べている。
        self.import_status_label = QLabel("")
        self.import_status_label.setWordWrap(True)
        self.import_status_label.setStyleSheet("font-size: 11px; color: #2f77d8;")
        center.addWidget(self.import_status_label)

        center.addStretch(1)

        root.addLayout(center, 1)

        # ---- 右: ツール ----
        right = QVBoxLayout()

        tool_group = QGroupBox("ツール（左クリック=描画／右クリック=消去）")
        tool_layout = QVBoxLayout(tool_group)
        self.tool_selector = ToolSelector(horizontal=False)
        self.tool_selector.tool_changed.connect(self._select_tool)
        self.tool_buttons = self.tool_selector.buttons  # 既存コードとの互換
        tool_layout.addWidget(self.tool_selector)
        right.addWidget(tool_group)

        color_group = QGroupBox("色")
        color_layout = QVBoxLayout(color_group)
        self.color_picker = CompactColorPicker(QColor(220, 40, 40, 255))
        self.color_picker.currentColorChanged.connect(self._on_color_changed)
        color_layout.addWidget(self.color_picker)
        right.addWidget(color_group)

        saturation_group = QGroupBox("絵全体の彩度調整")
        saturation_layout = QVBoxLayout(saturation_group)
        saturation_hint = QLabel(
            "1件選択時：今表示している絵（下書き含む）に、ドラッグ中はプレビュー、離すと確定します（Ctrl+Zで取り消せます）\n"
            "複数選択時：選択した中の保存済みの絵すべてに、離した時点でまとめて適用します"
        )
        saturation_hint.setStyleSheet("font-size: 11px; color: #666;")
        saturation_hint.setWordWrap(True)
        saturation_layout.addWidget(saturation_hint)

        slider_row = QHBoxLayout()
        slider_row.addWidget(QLabel("薄く"))
        self.saturation_slider = QSlider(Qt.Orientation.Horizontal)
        self.saturation_slider.setRange(-100, 100)
        self.saturation_slider.setValue(0)
        self.saturation_slider.sliderPressed.connect(self._on_saturation_slider_pressed)
        self.saturation_slider.valueChanged.connect(self._on_saturation_slider_changed)
        self.saturation_slider.sliderReleased.connect(self._on_saturation_slider_released)
        slider_row.addWidget(self.saturation_slider)
        slider_row.addWidget(QLabel("鮮やか"))
        saturation_layout.addLayout(slider_row)

        self.undo_batch_tint_btn = QPushButton("一括適用を元に戻す")
        self.undo_batch_tint_btn.setEnabled(False)
        self.undo_batch_tint_btn.setToolTip("直前の複数選択への一括適用だけを取り消せます（1回分のみ）")
        self.undo_batch_tint_btn.clicked.connect(self._on_undo_batch_tint)
        saturation_layout.addWidget(self.undo_batch_tint_btn)

        right.addWidget(saturation_group)

        # 「外部PNGをインポート...」は、編集中のキャンバスに直接効く操作なので
        # 中央列（キャンバスとプレビューの列）の一番下に移した。
        right.addStretch(1)
        root.addLayout(right, 1)

        # ボタン・コンボボックスが、スプリッタ／ウィンドウを縮めたときに
        # 文字が欠けるほど押し縮められないようにする（全タブ共通の対策）。
        fix_button_widths(content)

    # ---------------------------------------------------------------
    def _reload_variant_list(self, *_args):
        query = self.variant_search_box.text().strip().lower()

        def matches(name):
            # 絞り込み（検索語＋編集済み/未編集）の判定は3タブ共通のルール。
            # 状態名は英語のファイル名と日本語表示名のどちらでも引ける。
            return self.variant_filter.accepts(
                query, name in self.icons, name, VARIANT_LABELS_JA.get(name, "")
            )

        heart_matches = [n for n in HEART_VARIANTS if matches(n)]
        food_matches = [n for n in FOOD_VARIANTS if matches(n)]

        self.variant_list.clear()
        if heart_matches:
            self.variant_list.addItem(self._section_item("── 体力（heart） ──"))
            for name in heart_matches:
                self._add_variant_row(name)
        if food_matches:
            self.variant_list.addItem(self._section_item("── 満腹度（food） ──"))
            for name in food_matches:
                self._add_variant_row(name)

        self._update_variant_progress()

    def _update_variant_progress(self):
        total = len(HEART_VARIANTS) + len(FOOD_VARIANTS)
        done = len(self.icons)
        self.variant_progress_label.setText(f"編集済み: {done}/{total}")

    def _add_variant_row(self, name):
        item = self._variant_item(name)
        self.variant_list.addItem(item)
        row_widget = self._make_variant_row_widget(name)
        item.setSizeHint(row_widget.sizeHint())
        self.variant_list.setItemWidget(item, row_widget)

    def _section_item(self, text):
        item = QListWidgetItem(text)
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        return item

    def _make_variant_row_widget(self, name, name_col_width=190):
        """マーク／日本語名／ファイル名の順で、日本語名カラムの幅を揃えた行ウィジェットを作る。"""
        jp = VARIANT_LABELS_JA.get(name, "")

        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(4, 2, 4, 2)
        row_layout.setSpacing(8)

        marker_label = QLabel("●" if self.icons.get(name) is not None else "")
        marker_label.setObjectName("marker_label")
        marker_label.setFixedWidth(16)
        row_layout.addWidget(marker_label)

        name_label = QLabel(jp if jp else "―")
        name_label.setFixedWidth(name_col_width)
        row_layout.addWidget(name_label)

        file_label = QLabel(f"{name}.png")
        file_label.setStyleSheet("color: #888;")
        row_layout.addWidget(file_label)
        row_layout.addStretch(1)

        return row

    def _variant_item(self, name):
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, name)
        return item

    def _refresh_item_marks(self):
        for i in range(self.variant_list.count()):
            item = self.variant_list.item(i)
            name = item.data(Qt.ItemDataRole.UserRole)
            if name is None:
                continue
            widget = self.variant_list.itemWidget(item)
            if widget is None:
                continue
            marker_label = widget.findChild(QLabel, "marker_label")
            if marker_label is not None:
                marker_label.setText("●" if self.icons.get(name) is not None else "")
        self._update_variant_progress()

    def _on_variant_selected(self, current, previous):
        if current is None:
            return
        name = current.data(Qt.ItemDataRole.UserRole)
        if name is None:
            # セクション見出し行は選べないので、直前の選択に戻す
            self.variant_list.blockSignals(True)
            self.variant_list.setCurrentItem(previous)
            self.variant_list.blockSignals(False)
            return

        if self._dirty and not self.confirm_discard_if_dirty():
            # キャンセルされたので選択を戻す
            self.variant_list.blockSignals(True)
            self.variant_list.setCurrentItem(previous)
            self.variant_list.blockSignals(False)
            return

        self._current_variant = name
        label = VARIANT_LABELS_JA.get(name, "")
        self.variant_label.setText(f"編集中: {label}（{name}.png）" if label else f"編集中: {name}.png")
        existing = self.icons.get(name)
        self.canvas.blockSignals(True)
        self.canvas.clear()
        if existing is not None:
            self.canvas.load_image(existing)
        self.canvas.blockSignals(False)
        self.canvas.reset_undo_history()
        self._dirty = False
        self._update_dirty_indicator()
        self._load_original_preview(name)
        self._update_edit_preview()
        self._update_onion_skin()

    def has_unsaved_changes(self) -> bool:
        return self._dirty

    def confirm_discard_if_dirty(self, parent=None) -> bool:
        """
        未保存の編集があれば、保存/破棄/キャンセルを確認する。
        続行してよければTrue（Cancelされた場合はFalse）を返す。
        """
        if not self._dirty:
            return True
        box = QMessageBox(parent or self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("保存されていない変更")
        label = VARIANT_LABELS_JA.get(self._current_variant, "")
        target = f"{label}（{self._current_variant}.png）" if label else f"{self._current_variant}.png"
        box.setText(f"「{target}」に保存されていない変更があります。\nどうしますか？")
        box.setStandardButtons(
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel
        )
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        ret = box.exec()
        if ret == QMessageBox.StandardButton.Save:
            self._on_save_variant()
            return True
        elif ret == QMessageBox.StandardButton.Discard:
            self._on_revert_variant()
            return True
        else:
            return False

    def _on_save_variant(self):
        if self._current_variant is None:
            return
        self._commit_current_to_store()
        self._dirty = False
        self._refresh_item_marks()
        self._update_dirty_indicator()

    def _on_revert_variant(self):
        if self._current_variant is None:
            return
        existing = self.icons.get(self._current_variant)
        self.canvas.blockSignals(True)
        self.canvas.clear()
        if existing is not None:
            self.canvas.load_image(existing)
        self.canvas.blockSignals(False)
        self.canvas.reset_undo_history()
        self._dirty = False
        self._update_dirty_indicator()
        self._update_edit_preview()

    def _update_dirty_indicator(self):
        if self._dirty:
            self.dirty_indicator.setText("● 保存されていない変更があります（「保存する」を押してください）")
            self.dirty_indicator.setStyleSheet("color: #cc6600; font-weight: bold;")
        else:
            self.dirty_indicator.setText("")
        self.save_btn.setEnabled(self._dirty)
        self.revert_btn.setEnabled(self._dirty)
        self.undo_btn.setEnabled(self._current_variant is not None and self.canvas.can_undo())
        self.copy_btn.setEnabled(self._current_variant is not None and not self.canvas.is_empty())
        self.paste_btn.setEnabled(self._current_variant is not None and self._duplicate_source is not None)

    def _on_undo(self):
        if self._current_variant is None or not self.canvas.can_undo():
            return
        self.canvas.undo()

    def _on_copy_current(self):
        if self._current_variant is None or self.canvas.is_empty():
            return
        self._duplicate_source = self.canvas.to_image().copy()
        label = VARIANT_LABELS_JA.get(self._current_variant, "")
        display = f"{label}（{self._current_variant}.png）" if label else f"{self._current_variant}.png"
        self._duplicate_source_name = display
        self.duplicate_status_label.setText(f"複製元: {display}（コピー済み）")
        self._update_dirty_indicator()
        self._update_onion_skin()

    def _update_onion_skin(self):
        """
        オニオンスキン表示チェックボックスの状態に応じて、キャンバスの下敷き画像を更新する。
        優先順位: ①コピーした複製元があればそれ　②無ければバニラ本来の絵
        """
        if not self.onion_skin_checkbox.isChecked() or self._current_variant is None:
            self.canvas.set_onion_skin(None)
            return
        source = self._duplicate_source
        if source is None:
            source = self._get_original_reference_image(self._current_variant)
        self.canvas.set_onion_skin(source)

    def _on_paste_current(self):
        if self._current_variant is None or self._duplicate_source is None:
            return
        # 貼り付けは他の編集操作と同じく下書き扱い。「保存する」を押すまでは確定しない。
        self.canvas.load_image(self._duplicate_source.copy())

    # ---- 絵全体の彩度調整 ----
    def _on_saturation_slider_pressed(self):
        selected_names = [
            item.data(Qt.ItemDataRole.UserRole)
            for item in self.variant_list.selectedItems()
            if item.data(Qt.ItemDataRole.UserRole) is not None
        ]
        batch_targets = [n for n in selected_names if n in self.icons]

        if len(selected_names) > 1:
            # 複数選択時は、保存済みの絵がある物だけをまとめて対象にする
            if not batch_targets:
                self.saturation_slider.blockSignals(True)
                self.saturation_slider.setValue(0)
                self.saturation_slider.blockSignals(False)
                return
            self._saturation_batch_snapshot = {n: self.icons[n].copy() for n in batch_targets}
            self._saturation_snapshot = None
            return

        if self._current_variant is None or self.canvas.is_empty():
            # 対象が無ければ、つまんでも意味が無いのですぐ0に戻す
            self.saturation_slider.blockSignals(True)
            self.saturation_slider.setValue(0)
            self.saturation_slider.blockSignals(False)
            return
        self._saturation_batch_snapshot = None
        self._saturation_snapshot = self.canvas._snapshot()

    def _on_saturation_slider_changed(self, value):
        if self._saturation_batch_snapshot is not None:
            # 複数選択時はプレビューできる場所が無いため、ここでは何もせず
            # リリース時にまとめて計算・確定する（対象件数が多いと重くなるための配慮でもある）
            return
        if self._saturation_snapshot is None:
            return
        delta = value / 100.0  # -1.0 〜 +1.0
        size = self.canvas.size_px
        new_pixels = [[None] * size for _ in range(size)]
        for y in range(size):
            for x in range(size):
                px = self._saturation_snapshot[y][x]
                if px is None:
                    continue
                r, g, b, a = px
                if delta < 0:
                    # 「薄く」: 白を混ぜて明るいパステル調にする（ティント）。
                    # HSVの彩度だけを下げると同じ明るさのまま灰色に近づいてしまい、
                    # 意図した「薄いピンク」のような色合いにならないための対応。
                    factor = -delta  # 0.0〜1.0（1.0で真っ白）
                    nr = r + (255 - r) * factor
                    ng = g + (255 - g) * factor
                    nb = b + (255 - b) * factor
                    new_pixels[y][x] = (int(round(nr)), int(round(ng)), int(round(nb)), a)
                elif delta > 0:
                    # 「鮮やか」: 色相・明るさは保ったまま、HSVの彩度を上げる
                    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
                    s = max(0.0, min(1.0, s + delta))
                    nr, ng, nb = colorsys.hsv_to_rgb(h, s, v)
                    new_pixels[y][x] = (int(round(nr * 255)), int(round(ng * 255)), int(round(nb * 255)), a)
                else:
                    new_pixels[y][x] = px
        self.canvas.pixels = new_pixels
        self.canvas.update()
        self._update_edit_preview()

    def _on_saturation_slider_released(self):
        value = self.saturation_slider.value()

        if self._saturation_batch_snapshot is not None:
            if value != 0:
                delta = value / 100.0
                for name, original in self._saturation_batch_snapshot.items():
                    self.icons[name] = apply_saturation_delta_to_image(original, delta)
                self._last_removed_icons = None  # 別系統のUndo記録と混同しないようクリア
                self._last_batch_tint_snapshot = self._saturation_batch_snapshot
                self.undo_batch_tint_btn.setEnabled(True)
                self._reload_variant_list()
                self.import_status_label.setText(
                    f"選択した{len(self._saturation_batch_snapshot)}件に彩度調整を一括適用しました"
                )
            self._saturation_batch_snapshot = None
        elif self._saturation_snapshot is not None and value != 0:
            # 操作前の状態をUndo履歴に積んでから確定する（Ctrl+Zで戻せるように）
            self.canvas.push_undo_snapshot(self._saturation_snapshot)
            if self._current_variant is not None:
                self._dirty = True
                self._update_dirty_indicator()

        self._saturation_snapshot = None
        self.saturation_slider.blockSignals(True)
        self.saturation_slider.setValue(0)
        self.saturation_slider.blockSignals(False)

    def _on_undo_batch_tint(self):
        if not self._last_batch_tint_snapshot:
            return
        count = len(self._last_batch_tint_snapshot)
        self.icons.update(self._last_batch_tint_snapshot)
        self._last_batch_tint_snapshot = None
        self.undo_batch_tint_btn.setEnabled(False)
        self._reload_variant_list()
        if self._current_variant is not None:
            self._update_edit_preview()
        self.import_status_label.setText(f"一括適用した彩度調整（{count}件）を元に戻しました")

    def _shift_canvas(self, dx, dy):
        if self._current_variant is None:
            return
        self.canvas.shift(dx, dy)

    def _commit_current_to_store(self):
        if self._current_variant is None:
            return
        if self.canvas.is_empty():
            self.icons.pop(self._current_variant, None)
        else:
            self.icons[self._current_variant] = self.canvas.to_image()

    def _on_canvas_changed(self):
        # 描いただけでは確定しない。「保存する」ボタンが押されるまでは未保存扱い。
        if self._current_variant is not None:
            self._dirty = True
        self._update_dirty_indicator()
        self._update_edit_preview()

    def _select_tool(self, key):
        self.tool_selector.select(key)
        self.canvas.set_tool(key)

    def _on_color_changed(self, color: QColor):
        self.canvas.set_color((color.red(), color.green(), color.blue(), color.alpha()))

    def _on_color_picked(self, rgba):
        r, g, b, a = rgba
        self.color_picker.set_current_color(QColor(r, g, b, a), emit=False)
        self.canvas.set_color(rgba)

    def _on_remove_selected_variants(self):
        selected_names = []
        for item in self.variant_list.selectedItems():
            name = item.data(Qt.ItemDataRole.UserRole)
            if name is not None:
                selected_names.append(name)
        if not selected_names:
            return

        names_with_content = [n for n in selected_names if n in self.icons]
        if not names_with_content:
            return  # 保存済みの絵が無いものだけ選ばれていた場合は何もしない

        if not list_ui.confirm_removal(
            self, "選択の削除", len(names_with_content),
            "保存済みの絵が消えます。パックを生成済みで、そのzipが手元に残っていれば\n"
            "「既存パックから読み込む」で絵を復元できますが、それ以外に復元手段はありません。",
        ):
            return

        self.undo_remove_variants.store({n: self.icons[n] for n in names_with_content})

        for name in names_with_content:
            self.icons.pop(name, None)

        if self._current_variant in names_with_content:
            # 今開いていたバリアントも削除対象に含まれていた場合、編集エリアも空の状態にする
            self.canvas.blockSignals(True)
            self.canvas.clear()
            self.canvas.blockSignals(False)
            self.canvas.reset_undo_history()
            self._dirty = False
            self._update_dirty_indicator()
            self._update_edit_preview()

        self._reload_variant_list()

    def _on_undo_remove_variants(self):
        removed = self.undo_remove_variants.take()
        if not removed:
            return
        count = len(removed)
        self.icons.update(removed)
        self._reload_variant_list()
        if self._current_variant is not None:
            self._update_edit_preview()
        self.import_status_label.setText(f"削除した{count}件を元に戻しました")

    def _on_variant_list_context_menu(self, pos):
        item = self.variant_list.itemAt(pos)
        if item is None:
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        if name is None:
            return  # セクション見出し行

        label = VARIANT_LABELS_JA.get(name, "")
        display = f"{label}（{name}.png）" if label else f"{name}.png"

        menu = QMenu(self)
        copy_action = menu.addAction(f"「{display}」を複製元にする")
        copy_action.setEnabled(name in self.icons)
        paste_action = menu.addAction(f"複製元を「{display}」に貼り付け")
        paste_action.setEnabled(self._duplicate_source is not None)

        chosen = menu.exec(self.variant_list.mapToGlobal(pos))
        if chosen == copy_action:
            self._duplicate_source = self.icons[name].copy()
            self._duplicate_source_name = display
            self.duplicate_status_label.setText(f"複製元: {display}")
        elif chosen == paste_action:
            self._paste_duplicate_to(name)

    def _paste_duplicate_to(self, name):
        if self._duplicate_source is None:
            return
        # 通常のクリック選択と同じ経路を通す（未保存の下書きがあれば確認ダイアログが出る）
        for i in range(self.variant_list.count()):
            item = self.variant_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == name:
                self.variant_list.setCurrentRow(i)
                break
        if self._current_variant != name:
            return  # 切り替えがキャンセルされた

        # 貼り付けは「保存する」を押すまでは下書き扱い（他の編集操作と同じ挙動）
        self.canvas.load_image(self._duplicate_source.copy())

    def _on_import_png(self):
        if self._current_variant is None:
            QMessageBox.information(self, "インポート", "先に左の一覧からバリアントを選んでください")
            return
        path, _ = QFileDialog.getOpenFileName(self, "PNGをインポート", "", "PNG (*.png)")
        if not path:
            return
        self.import_png_path(path)

    def import_png_path(self, path):
        """指定パスのPNGを、現在選択中のバリアントに取り込む（ドラッグ&ドロップからも使用）。
        バリアントが未選択なら何もせずFalseを返す。"""
        if self._current_variant is None:
            return False
        try:
            img = Image.open(path)
        except Exception as e:
            QMessageBox.warning(self, "エラー", f"画像を読み込めませんでした: {e}")
            return False
        self.canvas.load_image(img)
        return True

    # ---------------------------------------------------------------
    # オリジナル（本物）アイコンの参照プレビュー
    # ---------------------------------------------------------------
    def set_reference_dir(self, hud_dir: str):
        """hud_dir は .../gui/sprites/hud フォルダ（中に heart/ と food相当のファイルがある想定）。"""
        self.reference_dir = hud_dir
        if self._current_variant is not None:
            self._load_original_preview(self._current_variant)
            self._update_onion_skin()

    def _on_choose_reference_dir(self):
        folder = QFileDialog.getExistingDirectory(
            self, "参照元フォルダを選択（.../gui/sprites/hud）"
        )
        if not folder:
            return
        self.set_reference_dir(folder)

    # ---------------------------------------------------------------
    # 既存のリソースパックから体力・満腹度アイコンを読み込む
    # ---------------------------------------------------------------
    def _get_start_dir_hint(self):
        # 直近で開いたOreHighlighterプロジェクトの場所があれば、それを最優先する
        # （「同じパックを読み込みたい」という意図に一番近いのはこちら）。
        # 無ければ、直近で読み込んだ素のテクスチャ（jar/フォルダ）の場所にフォールバックする。
        if self.get_project_dir_hint:
            try:
                hint = self.get_project_dir_hint()
                if hint and os.path.isdir(hint):
                    return hint
            except Exception:
                pass
        if self.get_source_dir_hint:
            try:
                hint = self.get_source_dir_hint()
                if hint and os.path.isdir(hint):
                    return hint
            except Exception:
                pass
        return os.path.expanduser("~")

    def _on_import_pack_folder(self):
        start_dir = self._get_start_dir_hint()
        folder = QFileDialog.getExistingDirectory(self, "既存のリソースパックフォルダを選択", start_dir)
        if not folder:
            return
        self._start_pack_import(folder)

    def _on_import_pack_zip(self):
        start_dir = self._get_start_dir_hint()
        zip_path, _ = QFileDialog.getOpenFileName(
            self, "既存のリソースパックzipを選択", start_dir, "Zip files (*.zip)"
        )
        if not zip_path:
            return
        try:
            extract_dir = tempfile.mkdtemp(prefix="ore_highlighter_import_")
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(extract_dir)
        except zipfile.BadZipFile:
            QMessageBox.critical(self, "エラー", "zipファイルとして読み込めませんでした。")
            return
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"読み込みに失敗しました: {e}")
            return
        self._start_pack_import(extract_dir)

    def _find_hud_dir(self, root):
        """
        root（パックのルートフォルダ）から .../textures/gui/sprites/hud を探す。
        zipの中身がさらに1階層フォルダに包まれているケースや、
        hudフォルダそのものを直接指定したケースにも対応する。
        """
        def looks_like_hud(d):
            if not os.path.isdir(d):
                return False
            heart_dir = os.path.join(d, HEART_SUBDIR)
            has_heart = os.path.isdir(heart_dir) and any(
                fn.lower().endswith(".png") for fn in os.listdir(heart_dir)
            )
            try:
                has_food = any(
                    fn.startswith("food_") and fn.lower().endswith(".png")
                    for fn in os.listdir(d)
                )
            except OSError:
                has_food = False
            return has_heart or has_food

        candidates = [
            os.path.join(root, "assets", "minecraft", "textures", "gui", "sprites", "hud"),
            root,  # root自体がすでにhudフォルダの場合
        ]
        try:
            entries = [e for e in os.listdir(root) if os.path.isdir(os.path.join(root, e))]
        except OSError:
            entries = []
        for e in entries:
            candidates.append(
                os.path.join(root, e, "assets", "minecraft", "textures", "gui", "sprites", "hud")
            )

        for c in candidates:
            if looks_like_hud(c):
                return c
        return None

    def _scan_pack_variant_images(self, hud_dir):
        found = {}
        heart_dir = os.path.join(hud_dir, HEART_SUBDIR)
        if os.path.isdir(heart_dir):
            for name in HEART_VARIANTS:
                p = os.path.join(heart_dir, f"{name}.png")
                if os.path.isfile(p):
                    try:
                        found[name] = Image.open(p).convert("RGBA")
                    except Exception:
                        pass
        food_dir = os.path.join(hud_dir, FOOD_SUBDIR) if FOOD_SUBDIR else hud_dir
        if os.path.isdir(food_dir):
            for name in FOOD_VARIANTS:
                p = os.path.join(food_dir, f"{name}.png")
                if os.path.isfile(p):
                    try:
                        found[name] = Image.open(p).convert("RGBA")
                    except Exception:
                        pass
        return found

    def _ask_import_mode(self):
        """戻り値: "backup_then_replace" / "merge" / "replace" / None(キャンセル)
        （ダイアログ本体はブロックエフェクトタブと共通の pack_backup 側にある）"""
        return pack_backup.ask_import_mode(
            self,
            "すでに保存済みのバリアントがあります。\n"
            "既存パックを読み込む前にどうしますか？",
        )

    def _do_backup_export(self):
        """現在保存済みのアイコンを、実際のリソースパックとして書き出す。
        続行してよければTrue。フローは pack_backup 側と共通。"""
        pack_name, output_dir = "OreHighlighter", None
        if self.get_pack_output_info:
            try:
                pack_name, output_dir = self.get_pack_output_info()
            except Exception:
                pack_name, output_dir = "OreHighlighter", None
        pack_name = pack_name or "OreHighlighter"
        self._backup_pack_name = pack_name
        self._backup_output_dir = output_dir

        return pack_backup.run_backup_export(
            self,
            has_content=bool(self.icons),
            pack_name=pack_name,
            output_dir=output_dir,
            write_pack=self._write_icon_backup_pack,
            confirm_text="今の保存済み内容を、どう書き出しますか？",
            missing_output_message=(
                "バックアップの保存先が設定されていません。\n"
                "「出力設定」タブで出力先フォルダを指定してください。"
            ),
            on_success=self._on_backup_saved,
        )

    def _write_icon_backup_pack(self, pack_root):
        """GUIアイコンだけを含むリソースパックを pack_root に書き出し、zip化する。
        戻り値は書き出したアイコンの件数。"""
        os.makedirs(pack_root, exist_ok=True)
        assets_root = os.path.join(pack_root, "assets", "minecraft")

        pack_mcmeta = {
            "pack": {
                "description": f"{self._backup_pack_name}（GUIアイコン バックアップ）",
                "min_format": [75, 0],
                "max_format": [100, 0],
            }
        }
        with open(os.path.join(pack_root, "pack.mcmeta"), "w", encoding="utf-8") as f:
            json.dump(pack_mcmeta, f, indent=2, ensure_ascii=False)

        written = self.export_all(assets_root)
        pack_backup.zip_pack_folder(pack_root)
        return written

    def _on_backup_saved(self, zip_path, written):
        self._last_backup_dir = self._backup_output_dir
        self.open_backup_folder_btn.setVisible(True)
        self._set_import_status(f"バックアップを保存しました: {zip_path}（{written}件）")

    def _on_open_backup_folder(self):
        pack_backup.open_backup_folder(self, getattr(self, "_last_backup_dir", None))

    def _start_pack_import(self, root_path):
        # 今編集中の未保存下書きがあれば先に確認する
        if self._dirty and not self.confirm_discard_if_dirty():
            return

        hud_dir = self._find_hud_dir(root_path)
        if not hud_dir:
            QMessageBox.warning(
                self, "見つかりません",
                "選択した場所から体力・満腹度アイコン（gui/sprites/hud）が見つかりませんでした。"
            )
            return

        found_images = self._scan_pack_variant_images(hud_dir)
        if not found_images:
            QMessageBox.information(
                self, "見つかりません",
                "体力・満腹度アイコンのファイルが1つも見つかりませんでした。"
            )
            return

        mode = "merge"
        if self.icons:
            mode = self._ask_import_mode()
            if mode is None:
                return
            if mode == "backup_then_replace":
                if not self._do_backup_export():
                    return
                mode = "replace"

        count = len(found_images)
        scope_note = (
            "既存の保存済みバリアントは全て消えます" if mode == "replace"
            else "同じ名前のバリアントだけが上書きされます（他は残ります）"
        )
        ret = QMessageBox.question(
            self, "読み込みの確認",
            f"{count}件のバリアントが見つかりました。読み込んで保存しますか？\n（{scope_note}）",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return

        if mode == "replace":
            self.icons = {}
        self.icons.update(found_images)

        self._reload_variant_list()
        self._refresh_canvas_for_current_variant()

        self._set_import_status(f"{count}件のバリアントを読み込みました。")

    def _refresh_canvas_for_current_variant(self):
        """
        self.icons の中身が外部から書き換わった後（パック読み込み・プロジェクト読み込みの後）に、
        今キャンバスで開いているバリアントがあれば表示をその内容に合わせ直す。
        開いているバリアントが無ければ何もしない（起動時のconfig.json読み込みでは無害な空振りになる）。
        """
        if self._current_variant is None:
            return
        existing = self.icons.get(self._current_variant)
        self.canvas.blockSignals(True)
        self.canvas.clear()
        if existing is not None:
            self.canvas.load_image(existing)
        self.canvas.blockSignals(False)
        self._dirty = False
        self._update_dirty_indicator()
        self._update_edit_preview()

    def _update_edit_preview(self):
        if self._current_variant is None:
            self.edit_preview.setText("（未選択）")
            return
        if self.canvas.is_empty():
            self.edit_preview.setText("（空）")
            return
        img = self.canvas.to_image()
        qimg = QImage(img.tobytes("raw", "RGBA"), img.width, img.height, QImage.Format.Format_RGBA8888)
        pixmap = QPixmap.fromImage(qimg).scaled(
            108, 108, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation
        )
        self.edit_preview.setPixmap(pixmap)

    def _get_original_reference_image(self, name):
        """指定バリアントの本物（バニラ）の画像をPIL.Imageとして返す。無ければNone。"""
        if not self.reference_dir:
            return None
        if name in HEART_VARIANTS:
            path = os.path.join(self.reference_dir, HEART_SUBDIR, f"{name}.png")
        elif name in FOOD_VARIANTS:
            path = os.path.join(self.reference_dir, FOOD_SUBDIR, f"{name}.png")
        else:
            path = None
        if not path or not os.path.exists(path):
            return None
        try:
            return Image.open(path).convert("RGBA")
        except Exception:
            return None

    def _load_original_preview(self, name):
        if not self.reference_dir:
            self.original_preview.setText("参照元なし\n（jarから読み込むか\n下のボタンで指定）")
            return

        img = self._get_original_reference_image(name)
        if img is None:
            self.original_preview.setText("このバリアントの\n元画像が\n見つかりません")
            return

        qimg = QImage(img.tobytes("raw", "RGBA"), img.width, img.height, QImage.Format.Format_RGBA8888)
        pixmap = QPixmap.fromImage(qimg).scaled(
            108, 108, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation
        )
        self.original_preview.setPixmap(pixmap)

    # ---------------------------------------------------------------
    def get_filled_count(self) -> int:
        return len(self.icons)

    def export_all(self, assets_root: str):
        """
        assets_root は "<pack_root>/assets/minecraft" を想定。
        この下に textures/gui/sprites/hud/heart/*.png ・ hud/food/*.png を書き出す。
        """
        if not self.icons:
            return 0

        heart_dir = os.path.join(assets_root, "textures", "gui", "sprites", "hud", HEART_SUBDIR)
        food_dir = os.path.join(assets_root, "textures", "gui", "sprites", "hud", FOOD_SUBDIR)

        written = 0
        for name, img in self.icons.items():
            if name in HEART_VARIANTS:
                out_dir = heart_dir
            elif name in FOOD_VARIANTS:
                out_dir = food_dir
            else:
                continue
            os.makedirs(out_dir, exist_ok=True)
            img.save(os.path.join(out_dir, f"{name}.png"))
            written += 1
        return written

    # ---- 設定の保存・復元 ----
    def serialize(self):
        """PNGバイト列に変換して辞書で返す（config.json保存用）。"""
        import base64, io as _io
        data = {}
        for name, img in self.icons.items():
            buf = _io.BytesIO()
            img.save(buf, format="PNG")
            data[name] = base64.b64encode(buf.getvalue()).decode("ascii")
        return data

    def deserialize(self, data: dict, merge: bool = False):
        """
        data: {バリアント名: base64のPNG} の辞書。
        merge=False（既定）: 今持っている内容を全部消してから読み込む
                              （config.json起動時の読み込みなど、まっさらな状態に対して使う）
        merge=True        : 同じ名前のバリアントだけ上書きし、他は残す
                              （既存プロジェクトへの「既存データを残したまま読み込む」用）
        """
        import base64, io as _io
        if not merge:
            self.icons = {}
        for name, b64str in (data or {}).items():
            try:
                raw = base64.b64decode(b64str)
                img = Image.open(_io.BytesIO(raw)).convert("RGBA")
                self.icons[name] = img
            except Exception:
                continue
        self._refresh_item_marks()
        self._refresh_canvas_for_current_variant()