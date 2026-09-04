"""
ブロックエフェクトタブ（BlockEffectTab）

main.py から切り出したモジュール。ブロックテクスチャの読み込み・対象ブロックの管理・
エフェクト設定・プレビュー・出力設定、そしてリソースパック本体の書き出しを担当する。

【ホストとの結合について】
このタブはパック生成の起点であり、GUIアイコン編集タブ・アイテムテクスチャ編集タブの
内容もまとめて1つのパックに書き出す。そのため、以下のものだけはホスト
（OreHighlighterWindow）から bind_host() で注入してもらう:

  - gui_icon_tab / item_tab      … export_all() などを呼ぶための他タブ参照
  - show_busy_dialog / close_busy_dialog … 「反映中...」ダイアログ（親ウィンドウ全体を
                                     setEnabled(False) にする方式のため、ホスト側が持つ）
  - notify_summary_changed       … ヘッダーの「生成予定」サマリーの再計算依頼

app_version と resource_path は main.py 側の定数・関数をコンストラクタで受け取る
（block_tab.py から main.py を import すると循環参照になるため）。

Copyright (c) 2026 旬茶
Licensed under the MIT License.
"""

import os
import sys
import io
import base64
import json
import shutil
import zipfile
import tempfile
import datetime

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QListWidget, QListWidgetItem, QLineEdit,
    QComboBox, QFileDialog, QMessageBox,
    QGroupBox, QFormLayout, QAbstractItemView, QSplitter, QFrame,
    QScrollArea
)
from PyQt6.QtGui import QMovie, QImage, QPixmap
from PyQt6.QtCore import Qt

from PIL import Image

from texture_effects import save_animated_texture
import effect_catalog as EC
from effect_catalog import DEFAULT_BLOCK_SETTINGS  # noqa: F401  （既存の外部参照との互換のため再輸出）
from effect_ui import EffectSettingsPanel
from texture_names import block_jp_name
from launcher_scan import find_prism_instances, find_launcher_jars
from ui_utils import fix_button_widths
import pack_backup
import list_ui

# エフェクトの一覧・既定値・フレーム生成は effect_catalog.py に集約した。
# 以前はこのファイルに EFFECT_NAMES と DEFAULT_BLOCK_SETTINGS を持っていたが、
# アイテムテクスチャ編集タブが別定義を持っていたため名前や機能に差が生まれていた。
#
# 【重要】設定ファイルに保存されるのは表示名ではなく内部キー（"blink" など）。
# 表示名は自由に変えてよいが、内部キーはリネームしないこと。
# 旧バージョンが保存した表示名は EC.normalize_effect() で読み替える。
EFFECT_KEYS = EC.BLOCK_EFFECT_KEYS


class BlockEffectTab(QWidget):
    def __init__(self, app_version="", resource_path=None, parent=None):
        super().__init__(parent)

        self.app_version = app_version
        # main.py の resource_path（exe化時の同梱リソース解決）。未指定なら実行ファイルと
        # 同じフォルダを見るだけの簡易版で代用する。
        self.resource_path = resource_path or (
            lambda rel: os.path.join(os.path.dirname(os.path.abspath(__file__)), rel)
        )

        # --- ホストから bind_host() で差し替えられるフック（既定は無害なダミー） ---
        self.gui_icon_tab = None
        self.item_tab = None
        self.show_busy_dialog = lambda message="反映中...": None
        self.close_busy_dialog = lambda dlg: None
        self.notify_summary_changed = lambda: None
        # 「読み込み」タブ（source_tab.SourceImportTab）へ状態表示をミラーするフック。
        # 読み込み系の操作は新タブから行うため、結果の文言も新タブ側に出す必要がある。
        self.report_source_status = lambda text: None

        self.textures_dir = None
        # 直近でテクスチャを読み込んだ場所のヒント。
        # 「既存のプロジェクトを開く」等のダイアログの初期位置や、
        # Prismインスタンス検出の初期選択に流用する。
        self._last_source_dir_hint = None
        # 直近で「既存のOreHighlighterプロジェクトを開く」に使った場所のヒント。
        # GUIアイコンタブの「フォルダから読み込む/zipから読み込む」の初期位置を
        # これに合わせることで、同じパックを何度も探し直さずに済むようにする。
        self._last_project_dir_hint = None
        self._last_prism_instance_name_hint = None
        self.output_dir = None
        self.pack_icon_path = None  # Noneならアプリ既定のアイコンをpack.pngとして使う
        self._synced_output_pack_root = None  # 出力先パック同期の確認を一度した後は聞き直さないための記録
        self._preview_gif_path = os.path.join(tempfile.gettempdir(), "ore_highlighter_preview.gif")

        self.target_blocks = []

        # 「読み込み」タブに並べるウィジェットを先に作っておく（親なしで生成され、
        # SourceImportTab のレイアウトに追加された時点で親が付く）。
        # on_open_folder() 等がこれらを参照するため、パネル構築より前に呼ぶこと。
        self.build_source_widgets()

        root = QHBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)
        # 各パネルはボタン・ラベルの内容量によって「最低でもこの幅は必要」という
        # サイズが決まってしまい、スプリッタで縮めようとしてもそこで頭打ちになっていた。
        # QScrollArea に収めることで、パネル自体の最小幅を切り離し（中身は必要なら
        # スクロールで見る）、左右パネルをもっと狭く・中央パネルをもっと広く
        # 調整できるようにする。
        splitter.addWidget(self._wrap_in_scroll_area(self._build_browse_panel(), min_width=180))
        splitter.addWidget(self._wrap_in_scroll_area(self._build_target_panel(), min_width=160))
        splitter.addWidget(self._wrap_in_scroll_area(self._build_editor_panel(), min_width=220))
        splitter.setSizes([300, 300, 560])
        # ウィンドウ拡大時、余った幅は中央（対象ブロック一覧）に優先的に配分する
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setStretchFactor(2, 1)

        # 「出力設定」（パック名・説明文・アイコン・出力先・Prism検出）は
        # 以前このタブの右側パネルに同居していたが、独立したタブに分離した。
        # ウィジェット（self.pack_name_edit 等）はこのクラスのインスタンス属性として
        # 保持されるので、on_generate() 等の他メソッドからは変更なしで参照できる。
        self.output_settings_tab = self._wrap_in_scroll_area(
            self._build_output_settings_panel(), min_width=280
        )

        self._update_pack_icon_preview()

    def _wrap_in_scroll_area(self, widget, min_width=200):
        """指定ウィジェットをQScrollAreaに収める。パネルの内容が多くても、
        スプリッタ側の最小幅は min_width まで縮められるようにするための共通処理。

        あわせて fix_button_widths() で、パネル内の各ボタン・コンボボックスが
        文字の欠けない幅より縮まないようにする（縮みきらない分は横スクロールで
        見る形にする）。"""
        fix_button_widths(widget)
        scroll = QScrollArea()
        scroll.setWidget(widget)
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(min_width)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        return scroll

    def bind_host(self, gui_icon_tab, item_tab,
                  show_busy_dialog, close_busy_dialog, notify_summary_changed):
        """ホスト（OreHighlighterWindow）が持つ依存物を注入する。
        UI構築の後、設定の自動読み込みより前に呼ぶこと。"""
        self.gui_icon_tab = gui_icon_tab
        self.item_tab = item_tab
        self.show_busy_dialog = show_busy_dialog
        self.close_busy_dialog = close_busy_dialog
        self.notify_summary_changed = notify_summary_changed

    # ---------------------------------------------------------------
    # ホスト（main.py）から使う小さな窓口
    # ---------------------------------------------------------------
    def set_status(self, text):
        self._set_status(text)

    def _set_status(self, text):
        """ブロックエフェクトタブの状態表示を更新し、同じ文言を「読み込み」タブにも出す。

        読み込み・プロジェクト取り込み・バックアップ書き出しは新タブ側のボタンから
        実行されるため、結果がブロックタブにしか出ないとユーザーから見えなくなる。"""
        self.status_label.setText(text)
        self.report_source_status(text)

    def get_target_count(self):
        return len(self.target_blocks)

    def get_pack_name(self):
        return self.pack_name_edit.text().strip() or "OreHighlighter"

    def get_pack_output_info(self):
        """GUIアイコン編集タブに渡す (パック名, 出力先) のタプル。"""
        return self.get_pack_name(), self.output_dir

    def get_source_dir_hint(self):
        return self._last_source_dir_hint

    def get_project_dir_hint(self):
        return self._last_project_dir_hint

    def load_textures_folder(self, path):
        """ドラッグ&ドロップ等で、展開済みのblockフォルダを直接読み込む。"""
        self.textures_dir = path
        self.folder_label.setText(f"フォルダ/jar: {path}")
        self._reload_browse_list()
        self._update_item_dir()
        self._update_source_hints(path)

    def load_jar(self, jar_path):
        self._load_jar_path(jar_path)

    def import_project(self, root_path):
        self._start_project_import(root_path)

    # ---------------------------------------------------------------
    # 設定（config.json）の入出力
    # ---------------------------------------------------------------
    def serialize(self):
        return {
            "textures_dir": self.textures_dir,
            "output_dir": self.output_dir,
            "target_blocks": self.target_blocks,
            "pack_name": self.pack_name_edit.text(),
            "pack_desc": self.pack_desc_edit.text(),
            "pack_icon_path": self.pack_icon_path,
        }

    def deserialize(self, cfg):
        """config.json 全体を受け取り、ブロックタブに関係するキーだけを反映する。
        （キーはv1.2.3以前と同じ位置＝トップレベルのまま。設定ファイルの互換性を保つため）"""
        self.textures_dir = cfg.get("textures_dir")
        if self.textures_dir and os.path.isdir(self.textures_dir):
            self.folder_label.setText(f"フォルダ/jar: {self.textures_dir}")
            self._reload_browse_list()
        self._update_item_dir()

        self.output_dir = cfg.get("output_dir")
        if self.output_dir:
            self.output_dir_label.setText(self.output_dir)

        self.pack_name_edit.setText(cfg.get("pack_name", "OreHighlighter"))
        self.pack_desc_edit.setText(cfg.get("pack_desc", ""))

        icon_path = cfg.get("pack_icon_path")
        self.pack_icon_path = icon_path if icon_path and os.path.exists(icon_path) else None
        self._update_pack_icon_preview()

        loaded_targets = cfg.get("target_blocks", [])
        self.target_blocks = []
        for b in loaded_targets:
            entry = dict(DEFAULT_BLOCK_SETTINGS)
            entry.update(b)
            # 旧バージョンは effect に表示名そのもの（"点滅" 等）を保存していたので、
            # 内部キーへ読み替える（effect_catalog.LEGACY_NAME_TO_KEY）。
            EC.normalize_settings(entry, DEFAULT_BLOCK_SETTINGS["effect"])
            if os.path.exists(entry.get("path", "")):
                self.target_blocks.append(entry)
        self._refresh_target_list()

    def _maybe_sync_output_pack(self):
        """
        出力先フォルダ（+ パック名）に既に生成済みのパックがある場合、
        「編集中のリソースパック」としてGUIアイコン編集・アイテムテクスチャ編集にも
        内容を反映するか確認する。ブロックエフェクトタブの出力先設定を軸に、
        3タブが同じパックを編集している状態を作りやすくするための機能。
        """
        if not self.output_dir:
            return
        pack_name = self.pack_name_edit.text().strip() or "OreHighlighter"
        pack_root = os.path.join(self.output_dir, pack_name)

        if pack_root == getattr(self, "_synced_output_pack_root", None):
            return  # 同じパックを既に確認済みなら、毎回は聞かない
        if not os.path.isfile(os.path.join(pack_root, "pack.mcmeta")):
            return  # そこにはまだパックが無い（これから生成する側）ので何もしない

        self._synced_output_pack_root = pack_root

        ret = QMessageBox.question(
            self, "既存パックを検出",
            f"出力先フォルダに、既に生成済みのパック「{pack_name}」が見つかりました。\n"
            f"GUIアイコン編集・アイテムテクスチャ編集にも、このパックの内容を反映しますか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return

        assets_root = os.path.join(pack_root, "assets", "minecraft")
        hud_dir = os.path.join(assets_root, "textures", "gui", "sprites", "hud")
        if os.path.isdir(hud_dir):
            self.gui_icon_tab._start_pack_import(pack_root)

        item_dir = os.path.join(assets_root, "textures", "item")
        if os.path.isdir(item_dir):
            busy = self.show_busy_dialog("アイテムテクスチャを同期しています…\nしばらくお待ちください")
            try:
                self._sync_item_images_from_pack(item_dir)
            finally:
                self.close_busy_dialog(busy)

    def _sync_item_images_from_pack(self, pack_item_dir):
        """
        既存パックの item テクスチャのうち、今読み込んでいるアイテムフォルダにも
        同名ファイルが存在するものだけを対象に、アイテムテクスチャ編集タブへ取り込む。
        （無関係なファイルまで対象に増やさないよう、実在するオリジナルとの対応を確認する）
        """
        if not self.item_tab.items_dir:
            self._set_status(
                "アイテムテクスチャの同期には、先にjar/フォルダの読み込みが必要です。"
            )
            return

        from item_texture_editor import validate_item_image, binarize_alpha

        synced = 0
        try:
            filenames = sorted(f for f in os.listdir(pack_item_dir) if f.lower().endswith(".png"))
        except OSError:
            return

        for fn in filenames:
            original_path = os.path.join(self.item_tab.items_dir, fn)
            if not os.path.exists(original_path):
                continue
            try:
                img = Image.open(os.path.join(pack_item_dir, fn))
            except Exception:
                continue
            ok, result = validate_item_image(img)
            if not ok:
                continue
            result = binarize_alpha(result)

            existing = next((t for t in self.item_tab.target_items if t["filename"] == fn), None)
            if existing is None:
                self.item_tab.target_items.append({"filename": fn, "path": original_path})
            cfg = self.item_tab._get_or_create_config(fn)
            cfg["custom_image"] = result
            synced += 1

        if synced:
            self.item_tab._refresh_target_list()
        self._set_status(f"出力先の既存パックから、アイテムテクスチャ{synced}件を同期しました。")

    def _build_browse_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)

        layout.addWidget(QLabel("テクスチャ一覧"))

        # テクスチャの読み込み元（jar / フォルダ / ランチャー自動検出）の指定は、
        # 独立した「読み込み」タブ（source_tab.SourceImportTab）に集約した。
        # このパネルには「読み込み済みテクスチャの絞り込み」と「対象への追加」だけを残す。
        self.browse_source_hint = QLabel("読み込み元の指定は「読み込み」タブで行います")
        self.browse_source_hint.setStyleSheet("font-size: 11px; color: #666;")
        self.browse_source_hint.setWordWrap(True)
        layout.addWidget(self.browse_source_hint)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("ブロック名で絞り込み（例: diamond）")
        self.search_box.textChanged.connect(self.on_search_changed)
        layout.addWidget(self.search_box)

        # 「編集済みのみ／未編集のみ」の排他チェックボックスは3タブ共通の部品。
        self.browse_filter = list_ui.EditedFilterBox()
        self.browse_filter.changed.connect(self._reload_browse_list)
        # 既存コード・テストとの互換のため、個々のチェックボックスも見えるようにしておく
        self.block_edited_only_checkbox = self.browse_filter.edited_only_checkbox
        self.block_unedited_only_checkbox = self.browse_filter.unedited_only_checkbox
        layout.addWidget(self.browse_filter)

        self.browse_list = QListWidget()
        self.browse_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        # 以前は「パネルが縦に伸びすぎないように」10行分で頭打ちにしていたが、
        # 読み込み元パネルを「読み込み」タブへ移して縦に余裕ができたので上限を外した。
        # 余った高さはすべてこの一覧に配分する（stretch=1）。
        # ※ここでstretchを付けないと、上のword-wrap付きQLabelが余白を吸って
        #   縦に間延びした見た目になる。
        self.browse_list.setStyleSheet(
            "QScrollBar:vertical { width: 18px; }"
            "QScrollBar::handle:vertical { background: #9aa5b1; border-radius: 7px; min-height: 24px; }"
            "QScrollBar::handle:vertical:hover { background: #7a8794; }"
        )
        layout.addWidget(self.browse_list, 1)

        add_btn = QPushButton("→ 対象ブロックに追加")
        add_btn.clicked.connect(self.on_add_to_targets)
        layout.addWidget(add_btn)

        return panel

    def build_source_widgets(self):
        """
        「読み込み」タブ（source_tab.SourceImportTab）に並べるウィジェットを作る。

        テクスチャの読み込み元の指定・ランチャーの自動検出・既存
        OreHighlighterプロジェクトを開く操作は、独立した「読み込み」タブに集約した。
        ただし出力設定タブと同じ方針で、ウィジェットの所有者とシグナル接続は
        引き続きこの BlockEffectTab のままにしてある。SourceImportTab は、ここで
        作ったウィジェットを自分のレイアウトに並べ直す（＝親を付け替える）だけ。

        こうすることで on_open_folder() / _load_jar_path() / _scan_launcher_jars()
        といった既存ロジックは self.folder_label / self.launcher_jar_list を
        そのまま参照でき、一切変更せずに済む。また、レイアウトへ追加されるまでは
        親なしウィジェットとして存在するだけなので、SourceImportTab を作らずに
        BlockEffectTab 単体を生成しても壊れない（テスト等）。
        """
        # ---- テクスチャの読み込み元 ----
        self.dnd_badge = QLabel("📥 D&D対応：jar / フォルダ / zip")
        self.dnd_badge.setStyleSheet(
            "background: #2f77d8; color: white; font-size: 10px; font-weight: bold;"
            "border-radius: 8px; padding: 2px 8px;"
        )

        self.folder_label = QLabel("フォルダ/jar: 未選択")
        self.folder_label.setWordWrap(True)

        self.auto_scan_label = QLabel("自動で探す（まずはこちらを試してください）")
        self.auto_scan_label.setStyleSheet("font-size: 11px; color: #666;")

        self.official_scan_btn = QPushButton("公式ランチャーから探す")
        self.official_scan_btn.setToolTip(
            "%appdata%\\.minecraft が標準の場所にあれば、フォルダ選択なしで\n"
            "即座にバージョンjarをスキャンします。見つからない場合だけ手動で選ぶ画面になります。"
        )
        self.official_scan_btn.clicked.connect(self.on_scan_official_launcher)

        self.prism_scan_btn = QPushButton("Prism Launcherから探す")
        self.prism_scan_btn.setToolTip(
            "%appdata%\\PrismLauncher が標準の場所にあれば、フォルダ選択なしで\n"
            "即座に全インスタンスのバージョンjarをスキャンします。見つからない場合だけ手動で選ぶ画面になります。"
        )
        self.prism_scan_btn.clicked.connect(self.on_scan_prism_launcher)

        self.launcher_scan_btn = QPushButton("その他の場所から探す...")
        self.launcher_scan_btn.setToolTip(
            "公式ランチャーやPrism Launcherを標準以外の場所にインストールしている場合、\n"
            "またはPrismの特定インスタンスのminecraftフォルダを直接指定したい場合に使ってください。\n"
            "選んだフォルダの中からバージョンjarを自動で探して、下の一覧に表示します。"
        )
        self.launcher_scan_btn.clicked.connect(self.on_scan_launcher_root)

        self.launcher_jar_list_label = QLabel("見つかったバージョン（jar）")

        self.launcher_jar_list = QListWidget()
        self.launcher_jar_list.setToolTip("クリックしたバージョンを読み込みます")
        # 5行分くらいの高さに固定し、それ以上はスクロールで見る
        row_h = self.launcher_jar_list.fontMetrics().height() + 10
        self.launcher_jar_list.setFixedHeight(row_h * 5 + 6)
        self.launcher_jar_list.setStyleSheet(
            "QScrollBar:vertical { width: 16px; }"
            "QScrollBar::handle:vertical { background: #9aa5b1; border-radius: 6px; min-height: 24px; }"
            "QScrollBar::handle:vertical:hover { background: #7a8794; }"
        )
        self.launcher_jar_list.itemClicked.connect(self.on_launcher_jar_selected)

        self.manual_source_label = QLabel(
            "手動で指定する（上で見つからない場合や、単体のjar/展開済みフォルダがある場合）"
        )
        self.manual_source_label.setStyleSheet("font-size: 11px; color: #666;")
        self.manual_source_label.setWordWrap(True)

        self.open_folder_btn = QPushButton("フォルダを開く...")
        self.open_folder_btn.clicked.connect(self.on_open_folder)

        self.open_jar_btn = QPushButton("jarから読み込む...")
        self.open_jar_btn.clicked.connect(self.on_open_jar)

        # ---- 既存のOreHighlighterプロジェクトを開く ----
        self.project_label = QLabel(
            "もらったパックや別PCで作ったパックの設定を丸ごと復元して、"
            "ブロック・GUIアイコン・アイテムの追加や削除を続けられます。"
        )
        self.project_label.setStyleSheet("font-size: 11px; color: #666;")
        self.project_label.setWordWrap(True)

        self.project_folder_btn = QPushButton("フォルダから開く...")
        self.project_folder_btn.clicked.connect(self.on_import_project_folder)

        self.project_zip_btn = QPushButton("zipから開く...")
        self.project_zip_btn.clicked.connect(self.on_import_project_zip)

        self.project_open_backup_btn = QPushButton("保存先フォルダを開く")
        self.project_open_backup_btn.setVisible(False)
        self.project_open_backup_btn.clicked.connect(self._on_open_project_backup_folder)


    def _build_target_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)

        layout.addWidget(QLabel("対象ブロック（パックに含める）"))

        self.target_count_label = QLabel("対象ブロック: 0件")
        self.target_count_label.setStyleSheet("font-size: 11px; color: #2f77d8; font-weight: bold;")
        layout.addWidget(self.target_count_label)

        self.target_list = QListWidget()
        self.target_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.target_list.itemSelectionChanged.connect(self.on_target_selection_changed)
        layout.addWidget(self.target_list)

        remove_btn = QPushButton("選択を削除")
        remove_btn.clicked.connect(self.on_remove_targets)
        layout.addWidget(remove_btn)

        self.undo_remove_blocks_btn = QPushButton("削除を元に戻す")
        self.undo_remove_blocks_btn.setToolTip("直前の「選択を削除」だけを取り消せます（1回分のみ）")
        self.undo_remove_blocks_btn.clicked.connect(self.on_undo_remove_blocks)
        layout.addWidget(self.undo_remove_blocks_btn)
        # 直近1回分の削除を覚えておく共通の入れ物（ボタンの有効/無効も面倒を見る）
        self.undo_remove_blocks = list_ui.UndoSlot(self.undo_remove_blocks_btn)

        # 「既存のOreHighlighterプロジェクトを開く」は「読み込み」タブへ移動した
        # （build_source_widgets() 参照）。ここには対象ブロックの管理だけを残す。
        return panel

    def _build_editor_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)

        self.editor_title = QLabel("（対象ブロックを選択してください）")
        self.editor_title.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.editor_title)

        # エフェクト設定のフォームは、アイテムテクスチャ編集タブと共通の
        # EffectSettingsPanel に一本化した（以前は両タブで別々に組み立てていた）。
        self.effect_panel = EffectSettingsPanel(
            "このブロックのエフェクト設定", EFFECT_KEYS, DEFAULT_BLOCK_SETTINGS
        )
        self.effect_panel.changed.connect(self.on_editor_changed)

        # 既存のコード・テストが self.effect_combo のように直接触れているので、
        # 個々のウィジェットへの参照はこれまで通りこのクラスからも見えるようにしておく。
        self.effect_combo = self.effect_panel.effect_combo
        self.frame_count_spin = self.effect_panel.frame_count_spin
        self.frametime_spin = self.effect_panel.frametime_spin
        self.thickness_spin = self.effect_panel.thickness_spin
        self.border_saturation_spin = self.effect_panel.border_saturation_spin
        self.border_brightness_spin = self.effect_panel.border_brightness_spin
        self.border_color_btn = self.effect_panel.border_color_btn
        self.gradient_band_count_spin = self.effect_panel.gradient_band_count_spin
        self.gradient_transparency_spin = self.effect_panel.gradient_transparency_spin
        self.dark_factor_spin = self.effect_panel.dark_factor_spin

        layout.addWidget(self.effect_panel)
        self._set_editor_enabled(False)

        preview_group = QGroupBox("プレビュー")
        preview_layout = QVBoxLayout(preview_group)
        self.preview_label = QLabel("対象ブロックを選択してプレビューを生成してください")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(140)
        preview_layout.addWidget(self.preview_label)
        preview_btn = QPushButton("選択中のブロックをプレビュー")
        preview_btn.clicked.connect(self.on_preview)
        preview_layout.addWidget(preview_btn)
        layout.addWidget(preview_group)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        return panel

    def _build_output_settings_panel(self):
        """
        「出力設定」タブの中身。以前はブロックエフェクトタブの右側パネル内に
        同居していたが、独立したタブに分離した（このタブ自体の見た目・場所が
        変わるだけで、パック名・出力先などのデータ自体は引き続き
        BlockEffectTab（このクラス）が保持し、on_generate() 等から
        self.pack_name_edit のように直接参照する）。
        """
        panel = QWidget()
        layout = QVBoxLayout(panel)

        output_group = QGroupBox("出力設定")
        output_form = QFormLayout(output_group)

        self.pack_name_edit = QLineEdit("OreHighlighter")
        output_form.addRow("パック名", self.pack_name_edit)

        self.pack_desc_edit = QLineEdit("Ore Highlighter Resource Pack")
        output_form.addRow("説明文", self.pack_desc_edit)

        icon_row = QHBoxLayout()
        self.pack_icon_preview = QLabel()
        self.pack_icon_preview.setFixedSize(32, 32)
        self.pack_icon_preview.setStyleSheet(
            "background: repeating-conic-gradient(#ccc 0% 25%, #999 0% 50%) 50% / 8px 8px;"
            "border: 1px solid #555;"
        )
        self.pack_icon_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pack_icon_btn = QPushButton("パックアイコンを選ぶ...")
        pack_icon_btn.clicked.connect(self.on_choose_pack_icon)
        pack_icon_reset_btn = QPushButton("デフォルトに戻す")
        pack_icon_reset_btn.setToolTip("未指定の場合、OreHighlighterのアプリアイコンがそのままパックのアイコンとして使われます")
        pack_icon_reset_btn.clicked.connect(self.on_reset_pack_icon)
        icon_row.addWidget(self.pack_icon_preview)
        icon_row.addWidget(pack_icon_btn)
        icon_row.addWidget(pack_icon_reset_btn)
        output_form.addRow("パックアイコン", icon_row)

        out_dir_row = QHBoxLayout()
        self.output_dir_label = QLineEdit()
        self.output_dir_label.setReadOnly(True)
        out_dir_btn = QPushButton("参照...")
        out_dir_btn.clicked.connect(self.on_choose_output_dir)
        out_dir_row.addWidget(self.output_dir_label)
        out_dir_row.addWidget(out_dir_btn)
        output_form.addRow("出力先(resourcepacksフォルダ)", out_dir_row)

        prism_row = QHBoxLayout()
        prism_detect_btn = QPushButton("Prism Launcherのインスタンスを検出")
        prism_detect_btn.clicked.connect(self.on_detect_prism_instances)
        self.prism_combo = QComboBox()
        self.prism_combo.setPlaceholderText("検出されたインスタンス")
        self.prism_combo.currentIndexChanged.connect(self.on_prism_instance_selected)
        prism_row.addWidget(prism_detect_btn)
        prism_row.addWidget(self.prism_combo)
        output_form.addRow("", prism_row)

        layout.addWidget(output_group)
        layout.addStretch(1)

        return panel

    def _set_editor_enabled(self, enabled: bool):
        self.effect_panel.set_editing_enabled(enabled)

    def _update_param_visibility(self):
        self.effect_panel.update_param_visibility()

    def _update_border_color_button(self):
        self.effect_panel._update_border_color_button()

    @property
    def _current_border_color(self):
        return self.effect_panel.border_color

    @_current_border_color.setter
    def _current_border_color(self, value):
        self.effect_panel.border_color = value

    def on_choose_border_color(self):
        self.effect_panel.on_choose_border_color()

    def on_open_folder(self):
        # 「ランチャーのルートフォルダから探す...」など他のダイアログの
        # 最終フォルダに引きずられないよう、明示的に開始位置を指定する。
        # 前回選んだテクスチャフォルダがあればその場所、無ければホームフォルダから。
        start_dir = os.path.dirname(self.textures_dir) if self.textures_dir else os.path.expanduser("~")
        folder = QFileDialog.getExistingDirectory(self, "テクスチャフォルダを選択", start_dir)
        if not folder:
            return
        self.textures_dir = folder
        self.folder_label.setText(f"フォルダ/jar: {folder}")
        self._reload_browse_list()
        self._update_item_dir()
        self._update_source_hints(folder)

    def _update_source_hints(self, path):
        """
        テクスチャの読み込み元（jarまたはフォルダ）から、後続の操作
        （既存プロジェクトを開く・Prismインスタンス検出）で使い回せる
        ヒントを更新する。パスの中に「instances/<名前>」が含まれていれば
        そのPrismインスタンスを特定できたとみなす。
        """
        norm = os.path.normpath(path)
        parts = norm.split(os.sep)
        if "instances" in parts:
            idx = parts.index("instances")
            if idx + 1 < len(parts):
                self._last_prism_instance_name_hint = parts[idx + 1]
                self._last_source_dir_hint = os.sep.join(parts[: idx + 2])
                return
        self._last_source_dir_hint = path if os.path.isdir(path) else os.path.dirname(path)

    def on_open_jar(self):
        # フォルダ選択ダイアログとは独立して、前回jarを選んだ場所を覚えておく。
        start_dir = getattr(self, "_last_jar_dir", None) or os.path.expanduser("~")
        jar_path, _ = QFileDialog.getOpenFileName(
            self, "Minecraftのjarファイルを選択（例: 26.2.jar / client.jar）", start_dir, "Jar files (*.jar)"
        )
        if not jar_path:
            return
        self._last_jar_dir = os.path.dirname(jar_path)
        self._load_jar_path(jar_path)

    def _appdata_dir(self):
        if sys.platform == "win32":
            return os.environ.get("APPDATA")
        return None

    def on_scan_official_launcher(self):
        appdata = self._appdata_dir()
        official_root = os.path.join(appdata, ".minecraft") if appdata else None
        if official_root and os.path.isdir(official_root):
            self._scan_launcher_jars(official_root)
        else:
            # 標準の場所に見つからない場合だけ、手動で選んでもらう
            root = QFileDialog.getExistingDirectory(
                self, "公式ランチャー（.minecraft）フォルダを選択", appdata or ""
            )
            if not root:
                return
            self._scan_launcher_jars(root)

    def on_scan_prism_launcher(self):
        appdata = self._appdata_dir()
        prism_root = os.path.join(appdata, "PrismLauncher") if appdata else None
        if prism_root and os.path.isdir(prism_root):
            self._scan_launcher_jars(prism_root)
        else:
            # 標準の場所に見つからない場合だけ、手動で選んでもらう
            root = QFileDialog.getExistingDirectory(
                self, "Prism Launcher のルートフォルダを選択", appdata or ""
            )
            if not root:
                return
            self._scan_launcher_jars(root)

    def on_scan_launcher_root(self):
        start_dir = self._appdata_dir() or ""
        root = QFileDialog.getExistingDirectory(
            self,
            "公式ランチャー（.minecraft）または Prism Launcher のルートフォルダを選択",
            start_dir,
        )
        if not root:
            return
        self._scan_launcher_jars(root)

    def _scan_launcher_jars(self, root):
        jars = find_launcher_jars(root)
        self._launcher_jars = jars

        self.launcher_jar_list.blockSignals(True)
        self.launcher_jar_list.clear()
        if jars:
            for label, _path in jars:
                self.launcher_jar_list.addItem(label)
            self._set_status(
                f"「{root}」から{len(jars)}件のバージョン(jar)が見つかりました。下の一覧から選んでください。"
            )
        else:
            self._set_status(
                "バージョン(jar)が見つかりませんでした。「jarから読み込む...」で直接指定してください。"
            )
        self.launcher_jar_list.blockSignals(False)

    def on_launcher_jar_selected(self, item):
        if not getattr(self, "_launcher_jars", None):
            return
        index = self.launcher_jar_list.row(item)
        if index < 0:
            return
        _label, jar_path = self._launcher_jars[index]
        self._load_jar_path(jar_path)

    def _load_jar_path(self, jar_path):
        self._update_source_hints(jar_path)
        prefix = "assets/minecraft/textures/block/"
        hud_prefix = "assets/minecraft/textures/gui/sprites/hud/"
        item_prefix = "assets/minecraft/textures/item/"
        busy = self.show_busy_dialog("テクスチャを読み込んでいます…\nしばらくお待ちください")
        try:
            with zipfile.ZipFile(jar_path, "r") as z:
                all_names = z.namelist()
                members = [m for m in all_names if m.startswith(prefix) and m.lower().endswith(".png")]
                hud_members = [m for m in all_names if m.startswith(hud_prefix) and m.lower().endswith(".png")]
                item_members = [m for m in all_names if m.startswith(item_prefix) and m.lower().endswith(".png")]
                if not members:
                    QMessageBox.warning(self, "エラー", "このjarの中にブロックテクスチャが見つかりませんでした。")
                    return

                extract_dir = tempfile.mkdtemp(prefix="ore_highlighter_")
                for m in members:
                    z.extract(m, extract_dir)
                for m in hud_members:
                    z.extract(m, extract_dir)
                for m in item_members:
                    z.extract(m, extract_dir)

            self.textures_dir = os.path.join(extract_dir, "assets", "minecraft", "textures", "block")
            self.folder_label.setText(f"フォルダ/jar: {jar_path}（jarから{len(members)}件展開）")
            self._reload_browse_list()
            self._update_item_dir()

            if hud_members:
                hud_dir = os.path.join(extract_dir, "assets", "minecraft", "textures", "gui", "sprites", "hud")
                self.gui_icon_tab.set_reference_dir(hud_dir)

            self._set_status(f"jarを読み込みました: {jar_path}")

        except zipfile.BadZipFile:
            QMessageBox.critical(self, "エラー", "このファイルはjar（zip形式）として読み込めませんでした。")
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"jarの読み込みに失敗しました: {e}")
        finally:
            self.close_busy_dialog(busy)

    def _update_item_dir(self):
        """textures_dir（.../textures/block）の兄弟フォルダとして .../textures/item を計算し、
        アイテムテクスチャ編集タブに反映する。"""
        if self.textures_dir:
            item_dir = os.path.join(os.path.dirname(self.textures_dir), "item")
        else:
            item_dir = None
        self.item_tab.set_items_dir(item_dir)

    def _make_name_row_widget(self, jp_name, tech_name, name_col_width=150):
        """日本語名 → ファイル名 の順で、日本語名カラムの幅を揃えた行ウィジェットを作る。"""
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(4, 2, 4, 2)
        row_layout.setSpacing(8)

        name_label = QLabel(jp_name if jp_name else "―")
        name_label.setFixedWidth(name_col_width)
        if not jp_name:
            name_label.setStyleSheet("color: #888;")
        row_layout.addWidget(name_label)

        file_label = QLabel(tech_name)
        file_label.setStyleSheet("color: #888;")
        row_layout.addWidget(file_label)
        row_layout.addStretch(1)

        return row

    def _reload_browse_list(self):
        self.browse_list.clear()
        if not self.textures_dir:
            return
        try:
            files = sorted(f for f in os.listdir(self.textures_dir) if f.lower().endswith(".png"))
        except OSError as e:
            QMessageBox.warning(self, "エラー", f"フォルダを読み込めませんでした: {e}")
            return

        query = self.search_box.text().strip().lower()
        targeted_filenames = {b["filename"] for b in self.target_blocks}

        for fn in files:
            jp = block_jp_name(fn)
            # 絞り込み（検索語＋編集済み/未編集）の判定は3タブ共通のルール。
            if not self.browse_filter.accepts(query, fn in targeted_filenames, fn):
                continue
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, fn)
            row_widget = self._make_name_row_widget(jp, fn)
            self.browse_list.addItem(item)
            item.setSizeHint(row_widget.sizeHint())
            self.browse_list.setItemWidget(item, row_widget)

    def on_search_changed(self, _text):
        self._reload_browse_list()

    def on_add_to_targets(self):
        if not self.textures_dir:
            return
        selected = self.browse_list.selectedItems()
        if not selected:
            QMessageBox.information(self, "追加", "テクスチャ一覧からブロックを選択してください")
            return

        existing_paths = {b["path"] for b in self.target_blocks}
        added = 0
        for item in selected:
            fn = item.data(Qt.ItemDataRole.UserRole)
            path = os.path.join(self.textures_dir, fn)
            if path in existing_paths:
                continue
            entry = {"filename": fn, "path": path}
            entry.update(DEFAULT_BLOCK_SETTINGS)
            self.target_blocks.append(entry)
            added += 1

        self._refresh_target_list()
        self.status_label.setText(f"{added}件を対象ブロックに追加しました")

    def on_remove_targets(self):
        selected_rows = sorted((self.target_list.row(i) for i in self.target_list.selectedItems()), reverse=True)
        if not selected_rows:
            return

        if not list_ui.confirm_removal(
            self, "対象ブロックの削除", len(selected_rows),
            "エフェクト設定（フレーム数・枠の太さなど）もすべて消え、再度追加しても\n"
            "初期設定からやり直しになります。パックを生成済みの場合でも、削除した\n"
            "設定を元のパラメータに戻す手段はありません。",
        ):
            return

        removed = []
        for row in selected_rows:  # 大きい行番号から削除するので、そのまま記録すれば元の順序で復元できる
            removed.append((row, self.target_blocks[row]))
            del self.target_blocks[row]
        removed.reverse()
        self.undo_remove_blocks.store(removed)
        self._refresh_target_list()
        self.status_label.setText(f"{len(removed)}件を対象ブロックから削除しました")

    def on_undo_remove_blocks(self):
        removed = self.undo_remove_blocks.take()
        if not removed:
            return
        for row, block in removed:
            insert_at = min(row, len(self.target_blocks))
            self.target_blocks.insert(insert_at, block)
        self._refresh_target_list()
        self.status_label.setText(f"削除した{len(removed)}件を元に戻しました")

    # ---------------------------------------------------------------
    # 既存のOreHighlighterプロジェクト（もらったパック）を読み込む
    # ---------------------------------------------------------------
    def on_import_project_folder(self):
        start_dir = self._last_source_dir_hint or os.path.expanduser("~")
        folder = QFileDialog.getExistingDirectory(self, "既存のリソースパックフォルダを選択", start_dir)
        if not folder:
            return
        # 開いたフォルダをそのまま次回生成時の出力先として引き継ぐ
        # （実際のパックフォルダは folder 自身か、その1つ下の可能性があるため
        # 正確な位置は _start_project_import 側で oreHighlighterProject.json の
        # 実際の場所から求め直す）。
        self._start_project_import(folder, origin_kind="folder", origin_path=folder)

    def on_import_project_zip(self):
        start_dir = self._last_source_dir_hint or os.path.expanduser("~")
        zip_path, _ = QFileDialog.getOpenFileName(
            self, "既存のリソースパックzipを選択", start_dir, "Zip files (*.zip)"
        )
        if not zip_path:
            return
        try:
            extract_dir = tempfile.mkdtemp(prefix="ore_highlighter_project_")
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(extract_dir)
        except zipfile.BadZipFile:
            QMessageBox.critical(self, "エラー", "zipファイルとして読み込めませんでした。")
            return
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"読み込みに失敗しました: {e}")
            return
        # 展開先は一時フォルダなので出力先の手がかりにはならない。
        # 元のzip自体の場所・ファイル名を出力先・パック名の引き継ぎに使う。
        self._start_project_import(extract_dir, origin_kind="zip", origin_path=zip_path)

    def _find_project_file(self, root):
        """root（パックのルートフォルダ）から oreHighlighterProject.json を探す。
        zipの中身がさらに1階層フォルダに包まれているケースにも対応する。"""
        candidates = [os.path.join(root, "oreHighlighterProject.json")]
        try:
            entries = [e for e in os.listdir(root) if os.path.isdir(os.path.join(root, e))]
        except OSError:
            entries = []
        for e in entries:
            candidates.append(os.path.join(root, e, "oreHighlighterProject.json"))
        for c in candidates:
            if os.path.isfile(c):
                return c
        return None

    def _start_project_import(self, root_path, origin_kind=None, origin_path=None):
        """
        既存のOreHighlighterプロジェクト（配布されたパック内の oreHighlighterProject.json）を
        読み込み、ブロック・GUIアイコン・アイテムテクスチャの3つをまとめて復元する。

        v1.2.5以前に生成されたパックには gui_icons / item_textures が含まれていないため、
        その場合は対象ブロックだけを復元する（エラーにはしない、後方互換）。

        origin_kind / origin_path:
            "folder" ならユーザーがQFileDialogで選んだフォルダそのもの、
            "zip" なら展開前の元のzipファイルのパス（展開先の一時フォルダには意味が
            無いため）。読み込みが成功したら、次回の「リソースパックを生成」が
            同じ場所を上書きするよう、出力先とパック名をここから引き継ぐ。
        """
        project_path = self._find_project_file(root_path)
        if not project_path:
            QMessageBox.warning(
                self, "見つかりません",
                "選択した場所に「oreHighlighterProject.json」が見つかりませんでした。\n"
                "OreHighlighter以外で作られたパック、または古いバージョンのOreHighlighterで\n"
                "作られたパックには、この設定ファイルは含まれていません。"
            )
            return

        try:
            with open(project_path, "r", encoding="utf-8") as f:
                project_data = json.load(f)
            loaded_blocks = project_data.get("target_blocks", [])
            loaded_gui_icons = project_data.get("gui_icons", {})
            loaded_item_data = project_data.get("item_textures", {})
            loaded_item_configs = loaded_item_data.get("item_configs", {})
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"プロジェクトファイルの読み込みに失敗しました: {e}")
            return

        if not loaded_blocks and not loaded_gui_icons and not loaded_item_configs:
            QMessageBox.information(self, "情報", "このプロジェクトには復元できる内容がありませんでした。")
            return

        if not self.textures_dir:
            QMessageBox.warning(
                self, "テクスチャ未読み込み",
                "先にブロックテクスチャ（jarまたはフォルダ）を読み込んでください。\n"
                "このプロジェクトの設定は、読み込んだテクスチャ・アイテム画像に対して適用されます。"
            )
            return

        # ---- ブロックの解決（テクスチャが実在するものだけを対象にする） ----
        resolved_blocks = []
        skipped_blocks = []
        for entry in loaded_blocks:
            fn = entry.get("filename")
            if not fn:
                continue
            path = os.path.join(self.textures_dir, fn)
            if os.path.exists(path):
                # 既定値を先に敷いてから上書きする。こうしておくと、v1.2.4より前の
                # バージョンで作られた（border_color等のキーが無い）プロジェクトを
                # 読み込んでも、パラメータ不足でエラーにならず既定値で補われる。
                new_entry = dict(DEFAULT_BLOCK_SETTINGS)
                new_entry.update(entry)
                # 旧形式のプロジェクト（effectが表示名）も読めるように内部キーへ正規化する
                EC.normalize_settings(new_entry, DEFAULT_BLOCK_SETTINGS["effect"])
                new_entry["path"] = path
                resolved_blocks.append(new_entry)
            else:
                skipped_blocks.append(fn)

        # ---- アイテムの解決（画像は実際には反映せず、件数の見積もりだけ先に行う。
        #      ブロックと同じく、確認ダイアログの時点で「何件見つからなかったか」を
        #      提示したいため。実際の反映は import_portable() にもう一度行わせる） ----
        loaded_item_targets = loaded_item_data.get("target_items", [])
        items_dir = self.item_tab.items_dir
        resolved_item_count = 0
        skipped_items_preview = []
        for entry in loaded_item_targets:
            fn = entry.get("filename")
            if not fn:
                continue
            path = os.path.join(items_dir, fn) if items_dir else None
            if path and os.path.exists(path):
                resolved_item_count += 1
            else:
                skipped_items_preview.append(fn)

        # ブロックだけのプロジェクトで1件も一致しない場合は、従来通りここで打ち切る
        # （GUIアイコンやアイテムの情報もあるなら、ブロックが0件でも続行する）
        if loaded_blocks and not resolved_blocks and not loaded_gui_icons and not loaded_item_configs:
            QMessageBox.warning(
                self, "一致するブロックがありません",
                "今読み込んでいるテクスチャの中に、このプロジェクトが使っているブロックが\n"
                "1つも見つかりませんでした。バージョン違いの可能性があります。"
            )
            return

        mode = "merge"
        if self.target_blocks or self.gui_icon_tab.get_filled_count() or self.item_tab.get_filled_count():
            mode = self._ask_project_import_mode()
            if mode is None:
                return
            if mode == "backup_then_replace":
                if not self._do_project_backup_export():
                    return
                mode = "replace"

        # ---- 読み込み前の確認（3種の件数と、見つからなかったものをまとめて表示） ----
        summary_parts = []
        if resolved_blocks:
            summary_parts.append(f"ブロック{len(resolved_blocks)}件")
        if loaded_gui_icons:
            summary_parts.append(f"GUIアイコン{len(loaded_gui_icons)}件")
        if resolved_item_count:
            summary_parts.append(f"アイテムテクスチャ{resolved_item_count}件")
        summary_text = "・".join(summary_parts) if summary_parts else "0件"

        skip_notes = []
        if skipped_blocks:
            skip_notes.append(f"ブロック{len(skipped_blocks)}件は今のテクスチャに見つかりませんでした")
        if skipped_items_preview:
            skip_notes.append(f"アイテム{len(skipped_items_preview)}件は今読み込んでいるアイテム画像に見つかりませんでした")
        scope_note = (
            "既存のブロック・GUIアイコン・アイテムはすべて消えます" if mode == "replace"
            else "同じ名前のものだけが上書きされます（他は残ります）"
        )
        skip_note_text = "\n（" + "、".join(skip_notes) + "）" if skip_notes else ""
        ret = QMessageBox.question(
            self, "読み込みの確認",
            f"{summary_text}の設定が見つかりました。読み込みますか？\n（{scope_note}）{skip_note_text}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return

        # ---- ブロックの反映 ----
        if mode == "replace":
            self.target_blocks = []
        existing_by_filename = {b["filename"]: i for i, b in enumerate(self.target_blocks)}
        for entry in resolved_blocks:
            fn = entry["filename"]
            if fn in existing_by_filename:
                self.target_blocks[existing_by_filename[fn]] = entry
            else:
                self.target_blocks.append(entry)

        # ---- GUIアイコン・アイテムテクスチャの反映 ----
        self.gui_icon_tab.deserialize(loaded_gui_icons, merge=(mode == "merge"))
        self.item_tab.import_portable(loaded_item_data, merge=(mode == "merge"))

        # ---- パックアイコンの反映 ----
        # 出力先・パック名と同じく「このプロジェクトを引き続き編集する」という
        # 意図に合わせ、マージ／置き換えに関わらず開いたプロジェクトのアイコンに揃える。
        # 埋め込みが無い（=開いた側がアプリ既定のアイコンを使っていた）場合も、
        # そちらに揃える（今の選択を残すと、別PCで再生成したときに意図せず
        # 元と違うアイコンのまま出力されてしまうため）。
        if "pack_icon_b64" in project_data:
            self._restore_custom_pack_icon(project_data.get("pack_icon_b64"))

        self._refresh_target_list()  # 内部で notify_summary_changed() も呼ばれる

        # ---- 出力先・パック名を、開いたプロジェクトの場所に合わせる ----
        # 「プロジェクトを開く」＝「このパックを引き続き編集したい」という意図のはずなので、
        # 次に「リソースパックを生成」を押したときに同じ場所を更新できるようにしておく。
        output_note = ""
        if origin_kind == "folder" and origin_path:
            # oreHighlighterProject.json の実際の場所（root_path自身か、その1つ下の
            # サブフォルダ）を正とする。root_pathをそのまま使うと、zipを手動で
            # 展開したときに生じる余計な1階層に引きずられることがあるため。
            pack_folder = os.path.dirname(project_path)
            new_output_dir = os.path.dirname(pack_folder)
            new_pack_name = os.path.basename(pack_folder)
            self.output_dir = new_output_dir
            self.output_dir_label.setText(new_output_dir)
            self.pack_name_edit.setText(new_pack_name)
            self._last_project_dir_hint = pack_folder
            output_note = f"\n出力先を「{new_output_dir}」（パック名: {new_pack_name}）に設定しました。"
        elif origin_kind == "zip" and origin_path:
            new_output_dir = os.path.dirname(origin_path)
            new_pack_name = os.path.splitext(os.path.basename(origin_path))[0]
            self.output_dir = new_output_dir
            self.output_dir_label.setText(new_output_dir)
            self.pack_name_edit.setText(new_pack_name)
            self._last_project_dir_hint = new_output_dir
            output_note = f"\n出力先を「{new_output_dir}」（パック名: {new_pack_name}）に設定しました。"

        self._set_status(
            f"プロジェクトから{summary_text}の設定を読み込みました。" + skip_note_text + output_note
        )

    def _ask_project_import_mode(self):
        """戻り値: "backup_then_replace" / "merge" / "replace" / None(キャンセル)
        （ダイアログ本体はGUIアイコン編集タブと共通の pack_backup 側にある）"""
        return pack_backup.ask_import_mode(
            self,
            "すでにブロック・GUIアイコン・アイテムのいずれかが設定されています。\n"
            "既存プロジェクトを読み込む前にどうしますか？",
        )

    def _do_project_backup_export(self):
        """今の内容（ブロック・GUIアイコン・アイテム）をパックとして書き出す。
        続行してよければTrue。フローは pack_backup 側と共通。"""
        has_content = bool(self.target_blocks) or (
            self.gui_icon_tab.get_filled_count() > 0
            or self.item_tab.get_filled_count() > 0
        )
        return pack_backup.run_backup_export(
            self,
            has_content=has_content,
            pack_name=self.get_pack_name(),
            output_dir=self.output_dir,
            write_pack=self._write_pack,
            confirm_text="今の対象ブロック・GUIアイコン・アイテムテクスチャの内容を、どう書き出しますか？",
            missing_output_message=(
                "バックアップの保存先が設定されていません。\n"
                "「出力設定」タブで出力先フォルダを指定してください。"
            ),
            error_hint=(
                "\n\n作りかけのファイルは出力先に残していません。\n"
                "今の設定はそのままなので、原因を直してからやり直せます。"
            ),
            on_success=self._on_project_backup_saved,
        )

    def _on_project_backup_saved(self, zip_path, _result):
        self._last_project_backup_dir = self.output_dir
        self.project_open_backup_btn.setVisible(True)
        self._set_status(f"バックアップを保存しました: {zip_path}")

    def _on_open_project_backup_folder(self):
        pack_backup.open_backup_folder(self, getattr(self, "_last_project_backup_dir", None))

    def _refresh_target_list(self):
        self.target_list.clear()
        for b in self.target_blocks:
            self.target_list.addItem(QListWidgetItem(self._target_label(b)))
        self.target_count_label.setText(f"対象ブロック: {len(self.target_blocks)}件")
        self.notify_summary_changed()
        if self.browse_filter.is_filtering():
            self._reload_browse_list()

    def _target_label(self, b):
        jp = block_jp_name(b["filename"])
        prefix = f'{jp}（{b["filename"]}）' if jp else b["filename"]
        return f'{prefix}  [{EC.display_name(b["effect"])}]'

    def _selected_target_indices(self):
        return sorted(self.target_list.row(i) for i in self.target_list.selectedItems())

    def on_target_selection_changed(self):
        indices = self._selected_target_indices()
        if not indices:
            self.editor_title.setText("（対象ブロックを選択してください）")
            self._set_editor_enabled(False)
            return

        if len(indices) == 1:
            fn = self.target_blocks[indices[0]]["filename"]
            jp = block_jp_name(fn)
            self.editor_title.setText(f"編集中: {jp}（{fn}）" if jp else f"編集中: {fn}")
        else:
            self.editor_title.setText(f"編集中: {len(indices)}件を一括編集")

        self._set_editor_enabled(True)
        self._load_editor_from_block(self.target_blocks[indices[0]])

    def _load_editor_from_block(self, block):
        self.effect_panel.load_from(block)

    def on_editor_changed(self, *_args):
        indices = self._selected_target_indices()
        if not indices:
            return
        new_settings = self.effect_panel.to_settings()
        for i in indices:
            self.target_blocks[i].update(new_settings)
        self._refresh_target_list_labels_only(indices)

    def _refresh_target_list_labels_only(self, indices):
        for i in indices:
            self.target_list.item(i).setText(self._target_label(self.target_blocks[i]))

    def _generate_frames_for(self, image, settings):
        # 生成ロジックはアイテムテクスチャ編集タブと共通（effect_catalog）。
        return EC.generate_frames(image, settings)

    def on_preview(self):
        indices = self._selected_target_indices()
        if not indices:
            QMessageBox.information(self, "プレビュー", "対象ブロックを選択してください")
            return

        block = self.target_blocks[indices[0]]
        try:
            image = Image.open(block["path"]).convert("RGBA")
        except Exception as e:
            QMessageBox.warning(self, "エラー", f"画像を読み込めませんでした: {e}")
            return

        frames = self._generate_frames_for(image, block)

        scale = 8
        big_frames = [f.resize((f.width * scale, f.height * scale), Image.NEAREST) for f in frames]
        durations = [block["frametime"] * 50 for _ in big_frames]
        big_frames[0].save(
            self._preview_gif_path, save_all=True, append_images=big_frames[1:],
            duration=durations, loop=0, disposal=2
        )

        movie = QMovie(self._preview_gif_path)
        self.preview_label.setMovie(movie)
        movie.start()
        self._current_movie = movie

    def on_choose_output_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "出力先フォルダ（resourcepacksフォルダ）を選択")
        if not folder:
            return
        self.output_dir = folder
        self.output_dir_label.setText(folder)
        self._maybe_sync_output_pack()

    def on_choose_pack_icon(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "パックアイコンにする画像を選択", "", "画像ファイル (*.png *.jpg *.jpeg *.bmp *.gif)"
        )
        if not path:
            return
        self.pack_icon_path = path
        self._update_pack_icon_preview()

    def on_reset_pack_icon(self):
        self.pack_icon_path = None
        self._update_pack_icon_preview()

    def _resolve_pack_icon_source(self):
        """pack.png の元にする画像パスを返す。カスタム指定が無ければアプリ既定のアイコン。"""
        if self.pack_icon_path and os.path.exists(self.pack_icon_path):
            return self.pack_icon_path
        default_icon = self.resource_path("icon.ico")
        if os.path.exists(default_icon):
            return default_icon
        return None

    def _encode_custom_pack_icon(self):
        """
        ユーザーがカスタム指定したパックアイコン（self.pack_icon_path）があれば、
        oreHighlighterProject.json に埋め込むためbase64文字列にして返す。
        指定が無い（アプリ既定のアイコンを使っている）場合はNone。
        """
        if not (self.pack_icon_path and os.path.exists(self.pack_icon_path)):
            return None
        try:
            img = Image.open(self.pack_icon_path).convert("RGBA")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return base64.b64encode(buf.getvalue()).decode("ascii")
        except Exception:
            return None

    def _restore_custom_pack_icon(self, pack_icon_b64):
        """
        _encode_custom_pack_icon() の逆。埋め込まれていたbase64を画像ファイルとして
        一時フォルダに書き出し、pack_icon_path をそこに向ける（既存の
        パス前提のコード：_resolve_pack_icon_source() 等をそのまま使うため）。
        pack_icon_b64がNoneなら「開いたプロジェクトはアプリ既定のアイコンを
        使っていた」という意味なので、こちらもNoneにそろえる。
        """
        if not pack_icon_b64:
            self.pack_icon_path = None
            self._update_pack_icon_preview()
            return
        try:
            raw = base64.b64decode(pack_icon_b64)
            img = Image.open(io.BytesIO(raw)).convert("RGBA")
        except Exception:
            return  # 壊れていた場合は今の設定に触らない
        icon_path = os.path.join(tempfile.gettempdir(), "ore_highlighter_imported_pack_icon.png")
        img.save(icon_path)
        self.pack_icon_path = icon_path
        self._update_pack_icon_preview()

    def _update_pack_icon_preview(self):
        source = self._resolve_pack_icon_source()
        if not source:
            self.pack_icon_preview.setText("?")
            return
        try:
            img = Image.open(source).convert("RGBA")
            qimg = QImage(img.tobytes("raw", "RGBA"), img.width, img.height, QImage.Format.Format_RGBA8888)
            pixmap = QPixmap.fromImage(qimg).scaled(
                32, 32, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            self.pack_icon_preview.setPixmap(pixmap)
        except Exception:
            self.pack_icon_preview.setText("?")

    def on_detect_prism_instances(self):
        self.status_label.setText("Prism Launcherのインスタンスを検索中...")
        QApplication.processEvents()

        instances = find_prism_instances()
        self.prism_combo.blockSignals(True)
        self.prism_combo.clear()
        self._prism_instances = instances

        if not instances:
            self.prism_combo.blockSignals(False)
            self.status_label.setText("Prism Launcherのインスタンスが見つかりませんでした")
            QMessageBox.information(
                self, "検出結果",
                "Prism Launcherのインスタンスが見つかりませんでした。\n"
                "「参照...」から手動でresourcepacksフォルダを選択してください。"
            )
            return

        for name, mc_path in instances:
            self.prism_combo.addItem(name)
        self.prism_combo.blockSignals(False)
        self.status_label.setText(f"{len(instances)}件のインスタンスが見つかりました")

        # テクスチャ読み込み時に「このPrismインスタンスを使っている」と判明していれば、
        # 同じインスタンスを自動的に選んで出力先まで設定する（毎回選び直す手間を省く）。
        hint_name = self._last_prism_instance_name_hint
        if hint_name:
            for i, (name, _mc_path) in enumerate(instances):
                if name == hint_name:
                    self.prism_combo.setCurrentIndex(i)
                    self.on_prism_instance_selected(i)
                    self.status_label.setText(
                        f"{len(instances)}件のインスタンスが見つかりました"
                        f"（テクスチャ読み込み元と同じ「{name}」を自動選択しました）"
                    )
                    break

    def on_prism_instance_selected(self, index):
        if index < 0 or not getattr(self, "_prism_instances", None):
            return
        name, mc_path = self._prism_instances[index]
        resourcepacks_dir = os.path.join(mc_path, "resourcepacks")
        os.makedirs(resourcepacks_dir, exist_ok=True)
        self.output_dir = resourcepacks_dir
        self.output_dir_label.setText(resourcepacks_dir)
        self.status_label.setText(f"出力先を「{name}」のresourcepacksフォルダに設定しました")
        self._maybe_sync_output_pack()

    def _confirm_overwrite_if_needed(self, pack_root, pack_name):
        """
        出力先に同名のリソースパックが既にある場合、Windowsのファイル置き換え確認と
        同じ考え方（更新日時・サイズを添えて Yes/No を聞く）で上書きしてよいか確認する。
        対象が無ければ何も聞かずTrueを返す。ユーザーが「いいえ」を選んだ場合はFalse。
        """
        zip_path = pack_root + ".zip"
        target_path = None
        if os.path.exists(zip_path):
            target_path = zip_path
        elif os.path.isdir(pack_root):
            # 通常はzipになっているはずだが、過去バージョンの生成物や手動展開などで
            # フォルダのまま残っているケースにも念のため備える。
            target_path = pack_root

        if target_path is None:
            return True

        try:
            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(target_path))
            mtime_text = mtime.strftime("%Y/%m/%d %H:%M")
            if os.path.isfile(target_path):
                size_text = f"{os.path.getsize(target_path) / 1024:.0f} KB"
            else:
                size_text = "フォルダ"
            detail = f"\n\n既存のファイル:\n更新日時: {mtime_text}　サイズ: {size_text}"
        except OSError:
            detail = ""

        ret = QMessageBox.question(
            self, "上書きの確認",
            f"出力先に同じ名前のリソースパック「{pack_name}」が既にあります。\n"
            f"上書きしますか？{detail}\n\n{target_path}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        return ret == QMessageBox.StandardButton.Yes

    def on_generate(self):
        gui_icon_count = self.gui_icon_tab.get_filled_count()
        item_count = self.item_tab.get_filled_count()
        if not self.target_blocks and gui_icon_count == 0 and item_count == 0:
            QMessageBox.information(
                self, "生成",
                "対象ブロック、GUIアイコン、アイテムテクスチャのいずれかを1つ以上作成してください"
            )
            return
        if not self.output_dir:
            QMessageBox.information(self, "生成", "出力先フォルダを選択してください")
            return

        pack_name = self.pack_name_edit.text().strip() or "OreHighlighter"
        pack_root = os.path.join(self.output_dir, pack_name)

        had_previous_zip = os.path.exists(pack_root + ".zip")
        if not self._confirm_overwrite_if_needed(pack_root, pack_name):
            return
        try:
            gui_written, item_written = self._write_pack(pack_root)
        except Exception as e:
            keep_note = (
                f"\n\n前回生成した「{pack_name}.zip」はそのまま残っています。"
                if had_previous_zip else ""
            )
            self.status_label.setText(f"生成に失敗しました: {e}")
            QMessageBox.critical(
                self, "エラー",
                f"生成に失敗しました: {e}\n\n"
                f"作りかけのファイルは出力先に残していません。"
                f"{keep_note}"
            )
            return

        zip_path = pack_root + ".zip"
        summary = f"ブロック{len(self.target_blocks)}件、GUIアイコン{gui_written}件、アイテムテクスチャ{item_written}件"
        self.status_label.setText(f"「{pack_name}.zip」を出力しました（{summary}）: {zip_path}")
        QMessageBox.information(
            self, "完了",
            f"リソースパックをzip形式で生成しました。\n\n{zip_path}\n\n{summary}\n\n"
            f"Minecraft内でリソースパックを再読み込みしてください（zipのまま読み込めます）。"
        )

    def _write_pack(self, pack_root):
        """
        現在の対象ブロック・GUIアイコン設定を使って、pack_root にパック一式を書き出す。
        on_generate（通常の生成）と、プロジェクト読み込み前のバックアップ書き出しの両方から使う共通処理。
        戻り値: (書き出したGUIアイコンの件数, 書き出したアイテムテクスチャの件数)

        途中で失敗した場合、作りかけのフォルダは必ず片付けてから例外を投げ直す。
        （resourcepacksフォルダに中途半端なパックフォルダが残ると、Minecraftが
        　それを「ブロックだけ適用されアイテムが欠けたパック」として読み込んでしまうため）
        """
        if os.path.exists(pack_root):
            shutil.rmtree(pack_root)
        try:
            return self._write_pack_contents(pack_root)
        except Exception:
            shutil.rmtree(pack_root, ignore_errors=True)
            raise

    def _write_pack_contents(self, pack_root):
        """_write_pack の中身。失敗時の後始末は呼び出し元（_write_pack）が担当する。"""
        assets_root = os.path.join(pack_root, "assets", "minecraft")
        tex_out_dir = os.path.join(assets_root, "textures", "block")
        os.makedirs(tex_out_dir, exist_ok=True)

        pack_name = self.pack_name_edit.text().strip() or "OreHighlighter"
        pack_mcmeta = {
            "pack": {
                "description": self.pack_desc_edit.text().strip() or pack_name,
                "min_format": [75, 0],
                "max_format": [100, 0],
            }
        }
        with open(os.path.join(pack_root, "pack.mcmeta"), "w", encoding="utf-8") as f:
            json.dump(pack_mcmeta, f, indent=2, ensure_ascii=False)

        # 他の人（または別PCの自分）がこのパックを開いて、ブロック・GUIアイコン・
        # アイテムテクスチャの設定を丸ごと復元・改造できるように、パラメータと
        # 編集済み画像（外部PNG・GUIアイコンの絵）をJSONとして埋め込む。
        # 元のブロックテクスチャ・アイテムのオリジナル絵そのものは含まない
        # （読み込み側で読み込み済みのjar/フォルダと突き合わせて解決するため）。
        # Minecraft側はこの余計なファイルを無視するだけなので実害は無い。
        item_data = self.item_tab.serialize()
        item_data["target_items"] = [
            {k: v for k, v in entry.items() if k != "path"}
            for entry in item_data["target_items"]
        ]
        project_data = {
            # 4: effect の値を表示名（"枠線のみ" 等）から内部キー（"outline" 等）に変更した。
            #    3以前のプロジェクトも effect_catalog.LEGACY_NAME_TO_KEY で読み込める。
            "format_version": 4,
            "generated_by": f"OreHighlighter v{self.app_version}",
            "target_blocks": [
                {k: v for k, v in block.items() if k != "path"}
                for block in self.target_blocks
            ],
            "gui_icons": self.gui_icon_tab.serialize(),
            "item_textures": item_data,
            # カスタムのパックアイコンを選んでいる場合のみ埋め込む（未指定＝アプリ既定の
            # アイコンを使っている場合はNone。既定アイコンはどのPCのOreHighlighterにも
            # 同梱されているため、わざわざ埋め込む必要が無い）。
            # これが無いと、別PCでこのプロジェクトを開いて再生成したときに、選んだ
            # カスタムアイコンのファイルパスはローカル環境にしか無いため見つからず、
            # 意図せずアプリ既定のアイコンに戻ってしまう。
            "pack_icon_b64": self._encode_custom_pack_icon(),
        }
        with open(os.path.join(pack_root, "oreHighlighterProject.json"), "w", encoding="utf-8") as f:
            json.dump(project_data, f, indent=2, ensure_ascii=False)

        icon_source = self._resolve_pack_icon_source()
        if icon_source:
            try:
                icon_img = Image.open(icon_source).convert("RGBA")
                # 正方形でない画像は中央を正方形にクロップしてから統一サイズにする
                w, h = icon_img.size
                if w != h:
                    side = min(w, h)
                    left = (w - side) // 2
                    top = (h - side) // 2
                    icon_img = icon_img.crop((left, top, left + side, top + side))
                icon_img = icon_img.resize((128, 128), Image.LANCZOS)
                icon_img.save(os.path.join(pack_root, "pack.png"))
            except Exception:
                pass  # アイコンの書き出しに失敗してもパック生成自体は続行する

        for block in self.target_blocks:
            image = Image.open(block["path"]).convert("RGBA")
            frames = self._generate_frames_for(image, block)
            save_animated_texture(
                frames, os.path.join(tex_out_dir, block["filename"]),
                frametime=block["frametime"],
                interpolate=(EC.normalize_effect(block["effect"]) != EC.BLINK),
            )

        gui_written = self.gui_icon_tab.export_all(assets_root)
        item_written = self.item_tab.export_all(assets_root)

        self._zip_pack_folder(pack_root)

        return gui_written, item_written

    def _zip_pack_folder(self, pack_root):
        """pack_root をzip化してフォルダを消す（実体は pack_backup 側の共通実装）。"""
        return pack_backup.zip_pack_folder(pack_root)
