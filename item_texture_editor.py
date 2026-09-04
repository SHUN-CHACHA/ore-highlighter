"""
アイテムテクスチャ編集タブ

ツルハシ・トーテムなど、assets/minecraft/textures/item/ 以下のアイテムアイコンを、
自分の好きな外部PNG画像に差し替えたり、ブロックエフェクトと同じレインボー/枠線/点滅の
アニメーションを付けたりするための機能。

- 外部PNG画像での差し替えは任意（差し替えなくても、オリジナルの絵にエフェクトだけ付けることもできる）
- エフェクトも任意（付けなければ、選んだ外部PNG画像 or オリジナルをそのまま静止画として使う）
- Minecraftのエンチャント効果そのもの（専用シェーダーによる光沢アニメーション）は
  リソースパックだけでは再現できないが、同じレインボー/点滅アニメーションの仕組みを
  流用することで、それらしい「派手な見た目」を付けられる

外部PNG画像の規格:
- 「正方形」かつ「512x512px以下」の画像のみ受け付ける（それ以外は取り込みを拒否する）
  自動クロップ・自動縮小は行わない。
  【注意】以前は64x64px以下に制限していた。手持ち時の3D表示（押し出し表現）で
  高解像度画像を使うと表示が崩れる不具合が過去に確認されていたための制限だったが、
  より高解像度の画像を使いたいという要望により512px上限に緩和した。GUI上のアイコン
  表示（インベントリ等）は問題ないはずだが、手に持った際の3D押し出し表現については
  高解像度だと崩れる場合がある点は変わらず残っているため、崩れが気になる場合は
  小さめの解像度（64px以下など）で用意することを推奨する。
- 取り込み時、輪郭の半透明ピクセル（アンチエイリアス）は自動で完全透明/完全不透明の
  どちらかに振り分けられる（binarize_alpha）。大きい元画像を縮小して用意した場合など、
  輪郭に中間的なアルファ値が残っていると、上記と同様に3D押し出し表現が崩れることが
  確認されたための対策

Copyright (c) 2026 旬茶
Licensed under the MIT License. 詳細は同梱の LICENSE ファイルを参照してください。
"""

import os
import io
import base64
import tempfile

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QLineEdit, QFileDialog, QMessageBox, QAbstractItemView,
    QGroupBox, QDialog, QInputDialog, QScrollArea, QFrame
)
from PyQt6.QtGui import QImage, QPixmap, QMovie
from PyQt6.QtCore import Qt, QItemSelectionModel

from ui_utils import fix_button_widths, NoticeButton
import list_ui
from PIL import Image

from texture_effects import save_animated_texture
import effect_catalog as EC
from effect_catalog import DEFAULT_ITEM_SETTINGS  # noqa: F401  （既存の外部参照との互換のため再輸出）
from effect_ui import EffectSettingsPanel
# ドット絵エディタ（キャンバス・ツール・編集ダイアログ）は共通部品。
# 以前は PixelEditDialog がこのファイルにあり、PixelCanvas を
# gui_icon_editor から import していた（タブ同士が依存し合う状態だった）。
from pixel_editor import PixelEditDialog

REQUIRED_ITEM_IMAGE_SIZE = 512

# エフェクトの一覧・既定値・フレーム生成は effect_catalog.py に集約した。
# 以前はこのファイルが独自の EFFECT_NAMES を持っていたため、同じ効果なのに
# ブロックタブと名前が違ったり（「レインボー（斜めグラデーション）」）、
# ブロック側に追加された帯の本数・透過度が反映されない機能差が生まれていた。
# 現在はブロックと同じエフェクトが全て使える。
EFFECT_KEYS = EC.ITEM_EFFECT_KEYS


def validate_item_image(img: Image.Image, required_size: int = REQUIRED_ITEM_IMAGE_SIZE):
    """
    画像が「正方形」かつ「required_size x required_size 以下」であるかを検証する。
    条件を満たさない場合は自動でクロップ・縮小はせず、そのまま拒否する
    （手持ち表示の3D押し出し表現は、高解像度すぎる画像だと崩れる場合があるため、
    　上限を設けてユーザーに正方形の画像を用意してもらう方式にしている）。

    戻り値: (True, RGBA変換済み画像) または (False, エラーメッセージ)
    """
    img = img.convert("RGBA")
    w, h = img.size
    if w != h:
        return False, (
            f"画像が正方形ではありません（{w}×{h}px）。\n"
            f"{required_size}×{required_size}pxの正方形画像を用意してください。"
        )
    if w > required_size:
        return False, (
            f"画像が大きすぎます（{w}×{h}px）。\n"
            f"{required_size}×{required_size}px以下の正方形画像を用意してください。"
        )
    return True, img


ALPHA_THRESHOLD = 128


def binarize_alpha(img: Image.Image, threshold: int = ALPHA_THRESHOLD) -> Image.Image:
    """
    半透明の輪郭ピクセル（アンチエイリアス）を、完全透明(0)か完全不透明(255)の
    どちらかに振り分ける。

    元画像（特に大きいサイズから縮小した画像）は、輪郭部分が中間的なアルファ値の
    グラデーションになっていることが多い。バニラのアイテムテクスチャは輪郭が常に
    0か255かのどちらかで作られているのに対し、この中間値が混ざっていると、
    Minecraft側の手持ちアイテムの3D押し出し表現（輪郭に沿った側面の自動生成）が
    不安定になり、表示が崩れることが確認されているための対策。
    """
    img = img.convert("RGBA")
    r, g, b, a = img.split()
    a = a.point(lambda v: 255 if v >= threshold else 0)
    return Image.merge("RGBA", (r, g, b, a))


def pil_to_qpixmap(img: Image.Image, size=96) -> QPixmap:
    img = img.convert("RGBA")
    qimg = QImage(img.tobytes("raw", "RGBA"), img.width, img.height, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimg).scaled(
        size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
    )


class ItemTextureEditorTab(QWidget):
    def __init__(self):
        super().__init__()
        self.items_dir = None  # assets/minecraft/textures/item フォルダ
        self.target_items = []  # [{"filename": "diamond_pickaxe.png", "path": "<items_dir>/diamond_pickaxe.png"}]
        self.item_configs = {}  # filename -> {"custom_image": PIL.Image|None, "effect": ..., パラメータ...}
        self._current_filename = None
        self._effect_target_filenames = []  # 複数選択時、エフェクト設定の適用先
        self._preview_gif_path = os.path.join(tempfile.gettempdir(), "ore_highlighter_item_preview.gif")
        self._current_movie = None
        self._build_ui()

    # ------------------------------------------------------------------
    # UI構築
    # ------------------------------------------------------------------
    def _build_ui(self):
        # タブの中身（左・中央・右の3列）をそのままselfの直下に置くと、
        # 内容量に応じた最小サイズがそのままウィンドウ全体の最小サイズに
        # 反映されてしまい、ウィンドウを縮められなくなる。
        # QScrollArea に収めることで、タブ自体の最小サイズを切り離す
        # （必要なら中身をスクロールして見る形にする）。
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)
        content = QWidget()
        scroll.setWidget(content)

        root = QHBoxLayout(content)

        # ---- 左: アイテムテクスチャ一覧 ----
        left = QVBoxLayout()
        header_row = QHBoxLayout()
        header_row.addWidget(QLabel("アイテムテクスチャ一覧　※●は編集済み"))
        dnd_badge = QLabel("📥 D&D対応：jar / フォルダ / PNG")
        dnd_badge.setStyleSheet(
            "background: #2f77d8; color: white; font-size: 10px; font-weight: bold;"
            "border-radius: 8px; padding: 2px 8px;"
        )
        header_row.addWidget(dnd_badge)
        header_row.addStretch(1)
        left.addLayout(header_row)
        self.items_dir_label = QLabel("フォルダ: 未選択（「読み込み」タブでjar/フォルダを読み込んでください）")
        self.items_dir_label.setWordWrap(True)
        self.items_dir_label.setStyleSheet("font-size: 11px; color: #666;")
        left.addWidget(self.items_dir_label)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("アイテム名で絞り込み（例: pickaxe）")
        self.search_box.textChanged.connect(self._reload_browse_list)
        left.addWidget(self.search_box)

        # 「編集済みのみ／未編集のみ」の排他チェックボックスは3タブ共通の部品。
        self.browse_filter = list_ui.EditedFilterBox()
        self.browse_filter.changed.connect(self._reload_browse_list)
        self.edited_only_checkbox = self.browse_filter.edited_only_checkbox
        self.unedited_only_checkbox = self.browse_filter.unedited_only_checkbox
        left.addWidget(self.browse_filter)

        self.browse_list = QListWidget()
        self.browse_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.browse_list.itemSelectionChanged.connect(self._on_browse_selection_changed)
        left.addWidget(self.browse_list)

        browse_preview_row = QHBoxLayout()
        browse_preview_row.addWidget(QLabel("プレビュー:"))
        self.browse_preview = QLabel("―")
        self.browse_preview.setFixedSize(48, 48)
        self.browse_preview.setStyleSheet(
            "background: repeating-conic-gradient(#ccc 0% 25%, #999 0% 50%) 50% / 8px 8px;"
            "border: 1px solid #555;"
        )
        self.browse_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        browse_preview_row.addWidget(self.browse_preview)
        browse_preview_row.addStretch(1)
        left.addLayout(browse_preview_row)

        add_btn = QPushButton("→ 対象アイテムに追加")
        add_btn.clicked.connect(self._on_add_targets)
        left.addWidget(add_btn)

        root.addLayout(left, 1)

        # ---- 中央: 対象アイテム一覧 ----
        mid = QVBoxLayout()
        mid.addWidget(QLabel("対象アイテム（外部PNG画像・エフェクト対象）　※●は設定済み"))
        self.target_list = QListWidget()
        self.target_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.target_list.itemSelectionChanged.connect(self._on_target_selected)
        mid.addWidget(self.target_list, 1)

        remove_btn = QPushButton("選択を削除")
        remove_btn.clicked.connect(self._on_remove_targets)
        mid.addWidget(remove_btn)

        self.undo_remove_targets_btn = QPushButton("削除を元に戻す")
        self.undo_remove_targets_btn.setToolTip("直前の「選択を削除」だけを取り消せます（1回分のみ）")
        self.undo_remove_targets_btn.clicked.connect(self._on_undo_remove_targets)
        mid.addWidget(self.undo_remove_targets_btn)
        # 直近1回分の削除を覚えておく共通の入れ物（ボタンの有効/無効も面倒を見る）
        self.undo_remove_targets = list_ui.UndoSlot(self.undo_remove_targets_btn)

        # アニメーションプレビューは中央列の下に置く。右列（編集エリア）に置くと
        # エフェクト設定の下までスクロールしないと見えず、設定を変えながら結果を
        # 確かめにくかったため。
        preview_group = QGroupBox("アニメーションプレビュー")
        preview_layout = QVBoxLayout(preview_group)
        self.effect_preview_label = QLabel("対象アイテムを選択してプレビューを生成してください")
        self.effect_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.effect_preview_label.setWordWrap(True)
        self.effect_preview_label.setFixedSize(220, 220)
        self.effect_preview_label.setStyleSheet(
            "background: repeating-conic-gradient(#eee 0% 25%, #ddd 0% 50%) 50% / 12px 12px;"
            "border: 1px solid #ccc;"
        )
        preview_layout.addWidget(self.effect_preview_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        preview_btn = QPushButton("選択中のアイテムをプレビュー")
        preview_btn.clicked.connect(self._on_preview)
        preview_layout.addWidget(preview_btn)
        mid.addWidget(preview_group)

        root.addLayout(mid, 1)

        # ---- 右: 編集エリア ----
        right = QVBoxLayout()
        self.editing_label = QLabel("（左の一覧から対象アイテムを選んでください）")
        self.editing_label.setStyleSheet("font-weight:bold;")
        self.editing_label.setWordWrap(True)
        right.addWidget(self.editing_label)

        preview_row = QHBoxLayout()

        orig_col = QVBoxLayout()
        orig_col.addWidget(QLabel("オリジナル"))
        self.original_preview = QLabel("―")
        self.original_preview.setFixedSize(96, 96)
        self.original_preview.setStyleSheet(
            "background: repeating-conic-gradient(#ccc 0% 25%, #999 0% 50%) 50% / 12px 12px;"
            "border: 1px solid #555;"
        )
        self.original_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        orig_col.addWidget(self.original_preview)
        preview_row.addLayout(orig_col)

        custom_col = QVBoxLayout()
        custom_col.addWidget(QLabel("外部PNG画像（任意）"))
        self.custom_preview = QLabel("未設定\n（オリジナルを使用）")
        self.custom_preview.setFixedSize(96, 96)
        self.custom_preview.setStyleSheet(
            "background: repeating-conic-gradient(#ccc 0% 25%, #999 0% 50%) 50% / 12px 12px;"
            "border: 1px solid #2f77d8;"
        )
        self.custom_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        custom_col.addWidget(self.custom_preview)
        preview_row.addLayout(custom_col)

        # 外部PNG画像の制約（正方形・サイズ上限・アルファの二値化・3D表示の崩れ）は
        # 常時表示すると場所を取るうえ、毎回読むものでもない。プレビュー枠の横に
        # 小さなボタンだけ置き、マウスオーバーでフローティング表示する。
        notice_col = QVBoxLayout()
        notice_col.addStretch(1)
        self.notice_btn = NoticeButton(notices=[
            "外部PNG画像は<b>「正方形・512×512px以下」</b>のみ受け付けます"
            "（それ以外は取り込めません）。自動クロップ・自動縮小は行いません。",
            "輪郭の半透明ピクセルは、取り込み時に自動で透明/不透明のどちらかに"
            "振り分けられます（手に持った際の3D表示の崩れ防止）。",
            "高解像度の画像は、手に持った際の3D表示が崩れる場合があります。"
            "気になる場合は<b>64px以下</b>で用意することを推奨します。",
            "参考：Minecraftのテクスチャは基本的に<b>「2のべき乗」の正方形"
            "（16, 32, 64, 128, 256, 512…）</b>で作られています。"
            "それ以外のサイズは正しく読み込まれない原因になることがあります。",
        ])
        notice_col.addWidget(self.notice_btn)
        notice_col.addStretch(1)
        preview_row.addLayout(notice_col)

        preview_row.addStretch(1)
        right.addLayout(preview_row)

        self.choose_btn = QPushButton("外部PNG画像を選ぶ...")
        self.choose_btn.clicked.connect(self._on_choose_image)
        right.addWidget(self.choose_btn)

        self.pixel_edit_btn = QPushButton("ドット絵エディタで編集する...")
        self.pixel_edit_btn.setToolTip(
            "ゼロから描く、または取り込んだ外部PNGをそのまま手直しする、\n"
            "どちらにも使えるドット絵エディタを開きます。"
        )
        self.pixel_edit_btn.clicked.connect(self._on_open_pixel_editor)
        right.addWidget(self.pixel_edit_btn)

        self.clear_image_btn = QPushButton("外部PNG画像を解除（オリジナルに戻す）")
        self.clear_image_btn.clicked.connect(self._on_clear_image)
        right.addWidget(self.clear_image_btn)

        # 画像の変更は「保存」ボタンを介さず、上の3つのボタンを押した瞬間にその場で
        # 確定する（GUIアイコン編集タブと違い、下書き状態を持たない）。ボタンが無いと
        # 「反映されたのか分かりにくい」ため、確定のたびにここへ一言表示する。
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("font-size: 11px; color: #2f77d8;")
        right.addWidget(self.status_label)

        # ---- エフェクト設定 ----
        # エフェクト設定のフォームは、ブロックエフェクトタブと共通の
        # EffectSettingsPanel に一本化した（以前は両タブで別々に組み立てていた）。
        self.effect_panel = EffectSettingsPanel(
            "エフェクト設定（任意・ブロックエフェクトと同じ仕組み）",
            EFFECT_KEYS, DEFAULT_ITEM_SETTINGS,
        )
        self.effect_panel.changed.connect(self._on_effect_param_changed)

        # 既存のコード・テストが直接触れているウィジェットは、これまで通り
        # このクラスからも参照できるようにしておく。
        self.effect_combo = self.effect_panel.effect_combo
        self.frame_count_spin = self.effect_panel.frame_count_spin
        self.frametime_spin = self.effect_panel.frametime_spin
        self.dark_factor_spin = self.effect_panel.dark_factor_spin

        right.addWidget(self.effect_panel)
        self._set_editor_enabled(False)

        right.addStretch(1)
        root.addLayout(right, 1)

        # ボタン・コンボボックスが、スプリッタ／ウィンドウを縮めたときに
        # 文字が欠けるほど押し縮められないようにする（全タブ共通の対策）。
        fix_button_widths(content)

    # ------------------------------------------------------------------
    # フォルダ・一覧
    # ------------------------------------------------------------------
    def set_items_dir(self, path):
        self.items_dir = path
        if path:
            self.items_dir_label.setText(f"フォルダ: {path}")
        else:
            self.items_dir_label.setText("フォルダ: 未選択（「読み込み」タブでjar/フォルダを読み込んでください）")
        self._reload_browse_list()

    def _reload_browse_list(self, *_args):
        # フィルタ・並び替えでリストを作り直しても、選択中の項目は見失わないようにする
        # （外部PNG選択などのその場確定操作のたびに呼ぶため、選択保持が重要）。
        selected_filenames = {
            i.data(Qt.ItemDataRole.UserRole) for i in self.browse_list.selectedItems()
        }
        self.browse_list.blockSignals(True)
        self.browse_list.clear()
        if not self.items_dir or not os.path.isdir(self.items_dir):
            self.browse_list.blockSignals(False)
            return
        try:
            files = sorted(f for f in os.listdir(self.items_dir) if f.lower().endswith(".png"))
        except OSError:
            self.browse_list.blockSignals(False)
            return
        query = self.search_box.text().strip().lower()

        for fn in files:
            # 「編集済み」は「対象に追加済みか」ではなく「実際に外部PNG画像や
            # エフェクトが設定されているか」で判定する（対象に追加しただけでは
            # まだ何も変わらないため、_has_content と揃える）。
            has_content = self._has_content(fn)
            if not self.browse_filter.accepts(query, has_content, fn):
                continue
            item = QListWidgetItem(list_ui.marked(has_content, fn))
            item.setData(Qt.ItemDataRole.UserRole, fn)
            # setSelected() はリストへ追加済みでないと効かないため、addItem() の後に呼ぶ
            self.browse_list.addItem(item)
            if fn in selected_filenames:
                item.setSelected(True)
        self.browse_list.blockSignals(False)
        self._on_browse_selection_changed()

    def _on_browse_selection_changed(self):
        """左のテクスチャ一覧をクリックしただけで、対象に追加する前にプレビューできるようにする。"""
        selected = self.browse_list.selectedItems()
        if len(selected) != 1 or not self.items_dir:
            self.browse_preview.setText("―" if not selected else "")
            self.browse_preview.setPixmap(QPixmap())
            return
        fn = selected[0].data(Qt.ItemDataRole.UserRole)
        path = os.path.join(self.items_dir, fn)
        try:
            img = Image.open(path).convert("RGBA")
            self.browse_preview.setPixmap(pil_to_qpixmap(img, 48))
        except Exception:
            self.browse_preview.setText("×")

    # ------------------------------------------------------------------
    # 対象アイテムの追加・削除
    # ------------------------------------------------------------------
    def _on_add_targets(self):
        selected = self.browse_list.selectedItems()
        if not selected:
            return
        existing = {b["filename"] for b in self.target_items}
        for item in selected:
            fn = item.data(Qt.ItemDataRole.UserRole)
            if fn in existing:
                continue
            path = os.path.join(self.items_dir, fn)
            self.target_items.append({"filename": fn, "path": path})
            existing.add(fn)
        self._refresh_target_list()

    def _on_remove_targets(self):
        selected_rows = sorted((self.target_list.row(i) for i in self.target_list.selectedItems()), reverse=True)
        if not selected_rows:
            return

        if not list_ui.confirm_removal(
            self, "対象アイテムの削除", len(selected_rows),
            "差し替え画像・エフェクト設定もすべて消えます。パックを生成済みで、\n"
            "そのzipが手元に残っていれば画像を復元できる場合がありますが、\n"
            "それ以外に復元手段はありません。",
        ):
            return

        removed = []
        for row in selected_rows:  # 大きい行番号から削除するので、そのまま記録すれば元の順序で復元できる
            entry = self.target_items[row]
            cfg = self.item_configs.pop(entry["filename"], None)
            removed.append((row, entry, cfg))
            del self.target_items[row]
        removed.reverse()
        self.undo_remove_targets.store(removed)
        self._refresh_target_list()

    def _on_undo_remove_targets(self):
        removed = self.undo_remove_targets.take()
        if not removed:
            return
        for row, entry, cfg in removed:
            insert_at = min(row, len(self.target_items))
            self.target_items.insert(insert_at, entry)
            if cfg is not None:
                self.item_configs[entry["filename"]] = cfg
        self._refresh_target_list()

    def _has_content(self, filename):
        cfg = self.item_configs.get(filename)
        if not cfg:
            return False
        effect = EC.normalize_effect(cfg.get("effect"), default=EC.NONE)
        return cfg.get("custom_image") is not None or effect != EC.NONE

    def _refresh_target_list(self):
        self.target_list.clear()
        for b in self.target_items:
            self.target_list.addItem(QListWidgetItem(
                list_ui.marked(self._has_content(b["filename"]), b["filename"])))
        # 左のアイテムテクスチャ一覧にも「●＝編集済み」を出しているため、フィルタの
        # ON/OFFに関わらず、内容が変わるたびに常に作り直して印を最新化する。
        self._reload_browse_list()

    def _reselect_current(self):
        target_filenames = set(self._effect_target_filenames) or (
            {self._current_filename} if self._current_filename else set()
        )
        if not target_filenames:
            return

        self.target_list.blockSignals(True)
        self.target_list.clearSelection()
        first_item = None
        for i, entry in enumerate(self.target_items):
            if entry["filename"] in target_filenames:
                item = self.target_list.item(i)
                item.setSelected(True)
                if first_item is None:
                    first_item = item
        if first_item is not None:
            # setCurrentRow()は選択自体をその1行だけに上書きしてしまうため、
            # NoUpdateで「現在位置」だけを動かし、複数選択はそのまま維持する。
            self.target_list.setCurrentItem(first_item, QItemSelectionModel.SelectionFlag.NoUpdate)
        self.target_list.blockSignals(False)

        # blockSignals中はitemSelectionChangedが飛ばないため、
        # _refresh_target_list()の再構築中に一時的にクリアされた
        # プレビュー・エディタの状態をここで明示的に復元する。
        if len(target_filenames) == 1 and self._current_filename:
            entry = next((e for e in self.target_items if e["filename"] == self._current_filename), None)
            if entry:
                self._populate_editor_for(entry)
        else:
            self._set_single_item_actions_enabled(False)
            self._set_editor_enabled(True)

    def _get_or_create_config(self, filename):
        if filename not in self.item_configs:
            self.item_configs[filename] = dict(DEFAULT_ITEM_SETTINGS, custom_image=None)
        return self.item_configs[filename]

    # ------------------------------------------------------------------
    # 編集エリア
    # ------------------------------------------------------------------
    def _set_editor_enabled(self, enabled: bool):
        self.effect_panel.set_editing_enabled(enabled)

    def _update_param_visibility(self):
        self.effect_panel.update_param_visibility()

    def _populate_editor_for(self, entry):
        """指定した対象アイテム1件の内容（オリジナル/外部PNGプレビュー・エフェクト設定）を
        編集エリアに反映する。単一選択時、および再選択による状態復元時に呼ぶ。"""
        self.editing_label.setText(f'編集中: {entry["filename"]}')

        try:
            orig_img = Image.open(entry["path"]).convert("RGBA")
            self.original_preview.setPixmap(pil_to_qpixmap(orig_img, 96))
        except Exception:
            self.original_preview.setText("読み込み\n失敗")
            self.original_preview.setPixmap(QPixmap())

        cfg = self._get_or_create_config(entry["filename"])
        custom = cfg.get("custom_image")
        if custom is not None:
            self.custom_preview.setPixmap(pil_to_qpixmap(custom, 96))
        else:
            self.custom_preview.setText("未設定\n（オリジナルを使用）")
            self.custom_preview.setPixmap(QPixmap())

        self._set_editor_enabled(True)
        self._set_single_item_actions_enabled(True)
        self._load_editor_from_config(cfg)

    def _set_single_item_actions_enabled(self, enabled: bool):
        """外部PNG選択・ドット絵エディタ・解除は、1件選択時のみ意味を持つ操作なので
        複数選択時は無効化する（エフェクト設定は複数選択でも一括適用できる）。"""
        self.choose_btn.setEnabled(enabled)
        self.pixel_edit_btn.setEnabled(enabled)
        self.clear_image_btn.setEnabled(enabled)

    def _on_target_selected(self):
        selected = self.target_list.selectedItems()
        rows = sorted(self.target_list.row(i) for i in selected)
        entries = [self.target_items[r] for r in rows]

        if not entries:
            self._current_filename = None
            self._effect_target_filenames = []
            self.editing_label.setText("（左の一覧から対象アイテムを選んでください）")
            self.original_preview.setText("―")
            self.original_preview.setPixmap(QPixmap())
            self.custom_preview.setText("未設定\n（オリジナルを使用）")
            self.custom_preview.setPixmap(QPixmap())
            self._set_editor_enabled(False)
            self._set_single_item_actions_enabled(False)
            return

        if len(entries) == 1:
            self._current_filename = entries[0]["filename"]
            self._effect_target_filenames = [entries[0]["filename"]]
            self._populate_editor_for(entries[0])
            return

        # ---- 複数選択：エフェクト設定のみ一括で編集できるようにする ----
        self._current_filename = None
        self._effect_target_filenames = [e["filename"] for e in entries]
        self.editing_label.setText(f"編集中: {len(entries)}件を一括編集（エフェクトのみ）")
        self.original_preview.setText("（複数選択中）")
        self.original_preview.setPixmap(QPixmap())
        self.custom_preview.setText("（複数選択中）\n個別に設定してください")
        self.custom_preview.setPixmap(QPixmap())
        self._set_single_item_actions_enabled(False)
        self._set_editor_enabled(True)
        # 代表として、最初に選んだ項目の現在の設定をエディタに表示する
        cfg = self._get_or_create_config(entries[0]["filename"])
        self._load_editor_from_config(cfg)

    def _load_editor_from_config(self, cfg):
        self.effect_panel.load_from(cfg)

    def _on_effect_param_changed(self, *_args):
        if not self._effect_target_filenames:
            return
        filenames = list(self._effect_target_filenames)
        current_filename = self._current_filename
        new_settings = self.effect_panel.to_settings()
        for fn in filenames:
            cfg = self._get_or_create_config(fn)
            cfg.update(new_settings)
        self._update_param_visibility()
        self._refresh_target_list()
        self._current_filename = current_filename
        self._effect_target_filenames = filenames
        self._reselect_current()

    def _on_choose_image(self):
        if not self._current_filename:
            QMessageBox.information(self, "アイテム未選択", "先に対象アイテムを一覧から選んでください。")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "外部PNG画像を選択", "", "画像ファイル (*.png *.jpg *.jpeg *.bmp *.gif)"
        )
        if not path:
            return
        self.import_image_path(path)

    def import_image_path(self, path):
        """指定パスの画像を、現在選択中(単一)のアイテムに取り込む（ドラッグ&ドロップからも使用）。
        アイテム未選択、または規格を満たさない場合はFalseを返す。"""
        if not self._current_filename:
            return False
        try:
            img = Image.open(path)
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"画像を読み込めませんでした: {e}")
            return False

        ok, result = validate_item_image(img)
        if not ok:
            QMessageBox.warning(self, "画像を受け付けられません", result)
            return False

        result = binarize_alpha(result)

        filename = self._current_filename
        cfg = self._get_or_create_config(filename)
        cfg["custom_image"] = result
        self.custom_preview.setPixmap(pil_to_qpixmap(result, 96))
        self._refresh_target_list()
        self._current_filename = filename
        self._effect_target_filenames = [filename]
        self._reselect_current()
        self.status_label.setText(f"「{filename}」に画像を反映しました。")
        return True

    def _on_open_pixel_editor(self):
        if not self._current_filename:
            QMessageBox.information(self, "アイテム未選択", "先に対象アイテムを一覧から選んでください。")
            return

        filename = self._current_filename
        cfg = self._get_or_create_config(filename)
        entry = next((t for t in self.target_items if t["filename"] == filename), None)

        original_image = None
        if entry and os.path.exists(entry["path"]):
            try:
                original_image = Image.open(entry["path"]).convert("RGBA")
            except Exception:
                original_image = None

        custom_image = cfg.get("custom_image")
        if custom_image is not None:
            # 既存の外部PNG画像がある場合は、そのサイズのまま手直しする
            # （ここでリサイズすると、せっかくの高解像度画像がぼやけてしまうため）
            size = custom_image.width
            initial_image = custom_image
        else:
            # ゼロから描く場合は、作業解像度を選んでもらう
            options = ["16", "32", "64"]
            default_size = REQUIRED_ITEM_IMAGE_SIZE
            if original_image and original_image.width == original_image.height and original_image.width <= REQUIRED_ITEM_IMAGE_SIZE:
                default_size = original_image.width
            default_text = str(default_size) if str(default_size) in options else "64"
            text, ok = QInputDialog.getItem(
                self, "作業解像度を選択",
                "ドット絵の作業解像度を選んでください（後から変更はできません）:",
                options, options.index(default_text), False
            )
            if not ok:
                return
            size = int(text)
            initial_image = None

        dialog = PixelEditDialog(
            self, size=size, initial_image=initial_image, original_image=original_image,
            title=f"- {filename}",
            # 保存時に輪郭の半透明ピクセルを二値化する（手持ち時の3D表示の崩れ防止）。
            # この後処理はアイテム固有なので、共通のエディタには持たせずここで渡す。
            post_process=binarize_alpha,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.result_image is not None:
            cfg["custom_image"] = dialog.result_image
            self.custom_preview.setPixmap(pil_to_qpixmap(dialog.result_image, 96))
            self._refresh_target_list()
            self._current_filename = filename
            self._reselect_current()
            self.status_label.setText(f"「{filename}」の絵を反映しました。")

    def _on_clear_image(self):
        if not self._current_filename:
            return
        filename = self._current_filename
        cfg = self.item_configs.get(filename)
        if cfg:
            cfg["custom_image"] = None
        self.custom_preview.setText("未設定\n（オリジナルを使用）")
        self.custom_preview.setPixmap(QPixmap())
        self._refresh_target_list()
        self._current_filename = filename
        self._reselect_current()
        self.status_label.setText(f"「{filename}」の外部PNG画像を解除しました（オリジナルに戻しました）。")

    # ------------------------------------------------------------------
    # エフェクト生成・プレビュー
    # ------------------------------------------------------------------
    def _generate_frames_for(self, image, settings):
        # 生成ロジックはブロックエフェクトタブと共通（effect_catalog）。
        # これにより、斜めグラデーションの帯の本数・透過度や枠線系エフェクトも
        # アイテムでそのまま使える（以前はブロック側にしか無かった）。
        return EC.generate_frames(image, settings)

    def _base_image_for(self, filename):
        """このアイテムに使うベース画像（外部PNG画像 があればそれ、無ければオリジナル）を返す。"""
        cfg = self.item_configs.get(filename)
        if cfg and cfg.get("custom_image") is not None:
            return cfg["custom_image"]
        entry = next((t for t in self.target_items if t["filename"] == filename), None)
        if entry and os.path.exists(entry["path"]):
            try:
                return Image.open(entry["path"]).convert("RGBA")
            except Exception:
                return None
        return None

    PREVIEW_BOX_SIZE = 200

    def _on_preview(self):
        if not self._current_filename:
            QMessageBox.information(self, "プレビュー", "対象アイテムを選択してください")
            return

        cfg = self._get_or_create_config(self._current_filename)
        base_img = self._base_image_for(self._current_filename)
        if base_img is None:
            QMessageBox.warning(self, "エラー", "元になる画像を読み込めませんでした。")
            return

        frames = self._generate_frames_for(base_img, cfg)

        # プレビュー枠(PREVIEW_BOX_SIZE)にちょうど収まるよう、元画像サイズに関わらず
        # 一定の最大辺サイズになるようスケールする（元画像サイズに関わらず枠からはみ出さない）。
        scale = max(1, self.PREVIEW_BOX_SIZE // max(base_img.width, 1))
        big_frames = [f.resize((f.width * scale, f.height * scale), Image.NEAREST) for f in frames]
        durations = [cfg["frametime"] * 50 for _ in big_frames]
        big_frames[0].save(
            self._preview_gif_path, save_all=True, append_images=big_frames[1:],
            duration=durations, loop=0, disposal=2
        )

        movie = QMovie(self._preview_gif_path)
        movie.setScaledSize(self.effect_preview_label.size())
        self.effect_preview_label.setMovie(movie)
        movie.start()
        self._current_movie = movie

    # ------------------------------------------------------------------
    # 生成・設定の保存/読み込み
    # ------------------------------------------------------------------
    def get_filled_count(self) -> int:
        return sum(1 for fn in self.item_configs if self._has_content(fn))

    def export_all(self, assets_root: str) -> int:
        """
        assets_root は "<pack_root>/assets/minecraft" を想定。
        外部PNG画像・エフェクトのいずれかが設定されている対象アイテムだけ
        textures/item/ 以下に書き出す。
        """
        targets = [fn for fn in self.item_configs if self._has_content(fn)]
        if not targets:
            return 0
        out_dir = os.path.join(assets_root, "textures", "item")
        os.makedirs(out_dir, exist_ok=True)
        count = 0
        for fn in targets:
            cfg = self.item_configs[fn]
            base_img = self._base_image_for(fn)
            if base_img is None:
                continue
            effect = EC.normalize_effect(cfg.get("effect"), default=EC.NONE)
            if effect == EC.NONE:
                base_img.save(os.path.join(out_dir, fn))
            else:
                frames = self._generate_frames_for(base_img, cfg)
                save_animated_texture(
                    frames, os.path.join(out_dir, fn),
                    frametime=cfg["frametime"],
                    # 点滅はコマ間を補間すると「フェード」になってしまうので補間しない
                    interpolate=(effect != EC.BLINK),
                )
            count += 1
        return count

    def serialize(self):
        """設定内容をJSON化可能な辞書にして返す（config.json保存用）。"""
        configs_data = {}
        for fn, cfg in self.item_configs.items():
            entry = {k: v for k, v in cfg.items() if k != "custom_image"}
            img = cfg.get("custom_image")
            if img is not None:
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                entry["custom_image_b64"] = base64.b64encode(buf.getvalue()).decode("ascii")
            configs_data[fn] = entry
        return {
            "target_items": self.target_items,
            "item_configs": configs_data,
        }

    def deserialize(self, data):
        data = data or {}
        self.target_items = data.get("target_items", [])
        self.item_configs = self._decode_item_configs(data.get("item_configs", {}))
        self._refresh_target_list()

    def _decode_item_configs(self, configs_data):
        """{filename: {..., "custom_image_b64": ...}} を
        {filename: {..., "custom_image": PIL.Image|None}} に変換する。
        deserialize()（config.json用）と import_portable()（配布パック用）の共通処理。"""
        result = {}
        for fn, entry in (configs_data or {}).items():
            cfg = dict(DEFAULT_ITEM_SETTINGS)
            cfg.update({k: v for k, v in entry.items() if k != "custom_image_b64"})
            # 旧バージョンは effect に表示名（"なし（静止画のみ）" 等）を保存していたので、
            # 内部キーへ読み替える（effect_catalog.LEGACY_NAME_TO_KEY）。
            EC.normalize_settings(cfg, DEFAULT_ITEM_SETTINGS["effect"])
            cfg["custom_image"] = None
            b64 = entry.get("custom_image_b64")
            if b64:
                try:
                    raw = base64.b64decode(b64)
                    cfg["custom_image"] = Image.open(io.BytesIO(raw)).convert("RGBA")
                except Exception:
                    pass
            result[fn] = cfg
        return result

    def import_portable(self, data, merge=False):
        """
        配布されたリソースパックに埋め込まれた oreHighlighterProject.json の
        "item_textures" セクションを読み込む。

        deserialize()（config.json用）との違いは、target_items の "path" が
        ローカル環境の絶対パスではなく含まれていない点（別PCへの配布を想定し、
        書き出し側であらかじめ取り除いてある）。ここでは self.items_dir
        （今読み込んでいるテクスチャの兄弟フォルダ）と突き合わせて、
        実在するファイルだけを対象として解決し直す。
        ブロックタブが target_blocks に対して行っている処理と同じ考え方。

        戻り値: (読み込めた対象アイテム件数, 元テクスチャが見つからず読み込めなかったファイル名のリスト)
        """
        data = data or {}
        loaded_targets = data.get("target_items", [])
        loaded_configs = data.get("item_configs", {})

        resolved_targets = []
        skipped = []
        for entry in loaded_targets:
            fn = entry.get("filename")
            if not fn:
                continue
            path = os.path.join(self.items_dir, fn) if self.items_dir else None
            if path and os.path.exists(path):
                resolved_targets.append({"filename": fn, "path": path})
            else:
                skipped.append(fn)

        resolved_filenames = {t["filename"] for t in resolved_targets}
        resolved_configs = self._decode_item_configs(
            {fn: cfg for fn, cfg in loaded_configs.items() if fn in resolved_filenames}
        )

        if merge:
            existing_by_filename = {t["filename"]: i for i, t in enumerate(self.target_items)}
            for entry in resolved_targets:
                fn = entry["filename"]
                if fn in existing_by_filename:
                    self.target_items[existing_by_filename[fn]] = entry
                else:
                    self.target_items.append(entry)
            self.item_configs.update(resolved_configs)
        else:
            self.target_items = resolved_targets
            self.item_configs = resolved_configs

        self._refresh_target_list()
        return len(resolved_targets), skipped
