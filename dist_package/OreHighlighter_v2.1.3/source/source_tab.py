"""
「読み込み」タブ（SourceImportTab）

それまで3つのタブに散らばっていた「読み込み口」を1画面に集約するタブ。

集約したもの:
  - テクスチャの読み込み元（公式/Prism Launcherの自動検出・その他の場所・
    jar・展開済みフォルダ）  … 旧: ブロックエフェクトタブ 左パネル上半分
  - 既存のOreHighlighterプロジェクトを開く（フォルダ/zip）
                              … 旧: ブロックエフェクトタブ 中央パネル下部
  - 参照元hudフォルダの指定／既存リソースパックからGUIアイコンを読み込む
                              … 旧: GUIアイコン編集タブ 中央パネル下部

【設計方針】
このタブは「並べ直すだけの器」であり、ロジックも状態も持たない。
ボタンやリストの実体は、これまで通り BlockEffectTab / GuiIconEditorTab が
build_source_widgets() で生成し、シグナル接続も各タブ側で完結している。
SourceImportTab は bind_tabs() でそれらを受け取り、自分のレイアウトに
addWidget() して親を付け替えるだけ。

こうしている理由:
  - on_open_folder() や _load_jar_path() など既存ロジックが参照している
    self.folder_label / self.launcher_jar_list をそのまま使えるので、
    移動に伴うロジック変更がゼロで済む（＝デグレしにくい）
  - 「出力設定」タブ（v2.0.2）で確立した方針と同じで、読む人が迷わない
  - SourceImportTab を作らなくても各タブ単体で生成でき、既存テストが壊れない

Copyright (c) 2026 旬茶
Licensed under the MIT License.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
    QScrollArea, QFrame
)

from ui_utils import fix_button_widths


class SourceImportTab(QWidget):
    """読み込み系の操作をまとめたタブ。中身は他タブが持つウィジェットの置き場所。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.block_tab = None
        self.gui_icon_tab = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # 内容量が多いタブなので、最初からQScrollAreaで包む。
        # （QTabWidget.minimumSizeHint() は全タブ中の最大値で決まるため、
        #   1タブでも大きいままだとウィンドウ全体を縮められなくなる）
        self._content = QWidget()
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(12, 12, 12, 12)
        self._layout.setSpacing(10)

        scroll = QScrollArea()
        scroll.setWidget(self._content)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("font-size: 12px; color: #2f77d8; font-weight: bold;")

    # ------------------------------------------------------------------
    def bind_tabs(self, block_tab, gui_icon_tab):
        """他タブが作ったウィジェットを受け取り、このタブに並べる。
        main.py の _build_ui() で、全タブを生成した後に一度だけ呼ぶこと。"""
        self.block_tab = block_tab
        self.gui_icon_tab = gui_icon_tab

        self._layout.addWidget(self._build_texture_source_group())
        self._layout.addWidget(self._build_project_group())
        self._layout.addWidget(self._build_gui_icon_group())
        self._layout.addWidget(self.status_label)
        self._layout.addStretch(1)

        # 読み込み結果の文言を、このタブの状態表示にもミラーしてもらう
        block_tab.report_source_status = self.set_status
        gui_icon_tab.report_source_status = self.set_status

        # ボタン・コンボボックスが、ウィンドウを縮めたときに文字が欠けるほど
        # 押し縮められないようにする（全タブ共通の対策 / ui_utils）。
        fix_button_widths(self._content)

    def set_status(self, text):
        self.status_label.setText(text)

    # ------------------------------------------------------------------
    def _build_texture_source_group(self):
        bt = self.block_tab
        group = QGroupBox("① テクスチャの読み込み元（Minecraft本体 / リソースパック / MOD）")
        layout = QVBoxLayout(group)

        badge_row = QHBoxLayout()
        badge_row.addWidget(bt.dnd_badge)
        badge_row.addStretch(1)
        layout.addLayout(badge_row)

        layout.addWidget(bt.folder_label)
        layout.addWidget(bt.auto_scan_label)

        auto_row = QHBoxLayout()
        auto_row.addWidget(bt.official_scan_btn)
        auto_row.addWidget(bt.prism_scan_btn)
        layout.addLayout(auto_row)

        layout.addWidget(bt.launcher_scan_btn)
        layout.addWidget(bt.launcher_jar_list_label)
        layout.addWidget(bt.launcher_jar_list)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color: #ccc; margin: 8px 0;")
        layout.addWidget(divider)

        layout.addWidget(bt.manual_source_label)

        manual_row = QHBoxLayout()
        manual_row.addWidget(bt.open_folder_btn)
        manual_row.addWidget(bt.open_jar_btn)
        layout.addLayout(manual_row)

        return group

    def _build_project_group(self):
        bt = self.block_tab
        group = QGroupBox("② 既存のOreHighlighterプロジェクトを開く")
        layout = QVBoxLayout(group)

        layout.addWidget(bt.project_label)

        row = QHBoxLayout()
        row.addWidget(bt.project_folder_btn)
        row.addWidget(bt.project_zip_btn)
        layout.addLayout(row)

        layout.addWidget(bt.project_open_backup_btn)
        return group

    def _build_gui_icon_group(self):
        gt = self.gui_icon_tab
        group = QGroupBox("③ 体力・満腹度アイコンの読み込み（GUIアイコン編集タブ用）")
        layout = QVBoxLayout(group)

        layout.addWidget(gt.ref_dir_btn)
        layout.addWidget(gt.import_pack_label)

        row = QHBoxLayout()
        row.addWidget(gt.import_pack_folder_btn)
        row.addWidget(gt.import_pack_zip_btn)
        layout.addLayout(row)

        layout.addWidget(gt.open_backup_folder_btn)
        return group
