"""
Minecraft 鉱石視認性向上ツール - GUI (PyQt6)

機能:
- テクスチャフォルダ／jarファイルから、ブロックPNGの一覧を検索・選択できる
- 「対象ブロック」として登録し、ブロックごとに個別のエフェクト（レインボー / 枠線 /
  レインボー+枠線 / 点滅）とパラメータを設定できる
- プレビュー（アニメーションGIF）で見た目を確認できる
- 登録した全ブロックをまとめてリソースパックとして生成・出力する
- 設定は終了時に自動保存、起動時に自動読み込みされる
- Prism Launcherのインスタンスを自動検出できる

このファイルの役割:
  アプリ全体の骨組み（ウィンドウ・ヘッダー・タブの組み立て）と、
  タブをまたぐ共通処理だけを持つ。各タブの中身は別モジュールにある。
    block_tab.py         … ブロックエフェクトタブ（＋リソースパックの書き出し本体）
    gui_icon_editor.py   … GUIアイコン編集タブ（体力・満腹度）
    item_texture_editor.py … アイテムテクスチャ編集タブ
    launcher_scan.py     … ランチャー/インスタンス探索（UI非依存の純粋関数）

  ブロックタブはパック生成の起点であり、他2タブの内容もまとめて1つのパックに
  書き出す。そのため _build_ui() の中で block_tab.bind_host(...) を呼び、
  他タブ参照・ビジーダイアログ・サマリー更新をブロックタブへ注入している。

Copyright (c) 2026 旬茶
Licensed under the MIT License. 詳細は同梱の LICENSE ファイルを参照してください。
（改変・商用利用・再配布は自由です。ただしこの著作権表示は削除しないでください）
"""

import sys
import os
import json
import zipfile
import tempfile
import shutil

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QMessageBox,
    QTabWidget, QTextEdit, QDialog
)
from PyQt6.QtGui import QDesktopServices, QIcon
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

from block_tab import BlockEffectTab
from gui_icon_editor import GuiIconEditorTab
from item_texture_editor import ItemTextureEditorTab
from source_tab import SourceImportTab
from ui_utils import SCROLLBAR_QSS, fix_button_widths

CONFIG_DEFAULT_NAME = "config.json"

if getattr(sys, "frozen", False):
    # PyInstallerでexe化されている場合: sys._MEIPASS 配下の一時展開フォルダではなく、
    # 実際にexeファイルが置かれているフォルダを使う（そうしないと終了時に消えてしまう）
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

# 「前回の設定を自動的に読み込む」ための保存先。
#
# 【なぜexe本体と同じフォルダに置かないか】
# 配布はGitHubのzipで、バージョンアップのたびに「新しいzipを展開して
# 古いフォルダごと入れ替える／上書きする」という運用になりやすい。
# 自動保存先がexeと同じフォルダ（旧: APP_DIR/config.json）だと、
# 新しいzipにはconfig.jsonが含まれていないため、フォルダを丸ごと
# 入れ替えると設定が消えてしまう。
# そこで、OS標準のユーザーデータ置き場（Windowsなら %APPDATA%）に
# 保存するようにし、exe本体のフォルダとは切り離す。
USER_DATA_DIR = os.path.join(
    os.environ.get("APPDATA") or os.path.expanduser("~/.oreHighlighter"),
    "OreHighlighter",
)
AUTO_CONFIG_PATH = os.path.join(USER_DATA_DIR, "config.json")

# v2.1.3より前は APP_DIR/config.json （exe本体と同じフォルダ）に自動保存していた。
# そちらにまだ設定が残っている場合、初回起動時に一度だけ新しい保存先へ引き継ぐ
# （_migrate_legacy_auto_config_if_needed() 参照）。
LEGACY_AUTO_CONFIG_PATH = os.path.join(APP_DIR, "config.json")


def resource_path(relative_path):
    """
    アイコンなど「exeに同梱したリソースファイル」の場所を返す。
    - 開発時（python main.py）: main.pyと同じフォルダ
    - exe化（PyInstaller --add-data で同梱）時: 一時展開フォルダ(sys._MEIPASS)
    どちらの場合でも正しいパスを返す。
    """
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(APP_DIR, relative_path)


APP_NAME = "Minecraft 鉱石視認性向上ツール（Ore Highlighter）"
APP_VERSION = "2.1.3"  # リリースごとに build_and_package.py の VERSION と合わせて更新してください
APP_COPYRIGHT = "Copyright (c) 2026 旬茶"
MANUAL_HTML_FILENAME = "使用マニュアル.html"

# ---- 起動時のバージョン更新確認 ----
# GitHub Releasesの最新版と現在のバージョンを比較し、新しい版があれば
# ウィンドウ上部にバナーで案内する。追加のpip依存を増やさないため、
# PyQt6に同梱のQtNetworkのみを使う。失敗（オフライン・GitHub側の問題等）は
# すべて静かに無視し、起動やその他の動作を一切妨げない。
GITHUB_REPO = "SHUN-CHACHA/homekura-live"
GITHUB_RELEASES_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
GITHUB_RELEASES_PAGE_URL = f"https://github.com/{GITHUB_REPO}/releases/latest"
ENABLE_UPDATE_CHECK = True  # テストではFalseに差し替えてネットワークアクセスを止める


def _parse_version_tuple(version_str):
    """"v2.1.2" や "2.1.2" のようなバージョン文字列を (2, 1, 2) のようなタプルに変換する。
    数字として解釈できない部分は無視する（例: "2.1.2-beta" -> (2, 1, 2)）。
    解釈できる数字が1つも無ければ None を返す。"""
    if not version_str:
        return None
    s = version_str.strip()
    if s.lower().startswith("v"):
        s = s[1:]
    parts = []
    for chunk in s.split("."):
        digits = ""
        for ch in chunk:
            if ch.isdigit():
                digits += ch
            else:
                break
        if digits == "":
            break
        parts.append(int(digits))
    if not parts:
        return None
    return tuple(parts)


def is_newer_version(remote_version_str, current_version_str) -> bool:
    """remote_version_str が current_version_str より新しければ True。
    どちらかが解釈できない場合は False（＝案内しない）を返す。"""
    remote = _parse_version_tuple(remote_version_str)
    current = _parse_version_tuple(current_version_str)
    if remote is None or current is None:
        return False
    return remote > current

MIT_LICENSE_EN = """MIT License

Copyright (c) 2026 旬茶

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE."""

MIT_LICENSE_JA = """MITライセンス（日本語訳・参考）

Copyright (c) 2026 旬茶

以下に定める条件に従う場合に限り、本ソフトウェアおよび関連文書のファイル（以下「本ソフトウェア」）の複製を
取得するすべての人に対し、本ソフトウェアを無制限に扱うことを無償で許可します。これには、本ソフトウェアの複製を
使用、複写、変更、結合、掲載、頒布、サブライセンス、および/または販売する権利、および本ソフトウェアを提供する
相手方にこれらの行為を許可する権利も無制限に含まれます。

上記の著作権表示および本許諾表示を、本ソフトウェアのすべての複製または重要な部分に記載するものとします。

本ソフトウェアは「現状のまま」で、明示であるか黙示であるかを問わず、何らの保証もなく提供されます。
ここでいう保証とは、商品性、特定目的への適合性、および権利非侵害についての保証も含みますが、それに限定されるものではありません。
作者または著作権者は、契約行為、不法行為、またはそれ以外であろうと、本ソフトウェアに起因または関連し、あるいは
本ソフトウェアの使用またはその他の扱いによって生じる一切の請求、損害、その他の義務について何らの責任も負わないものとします。

※この日本語訳は参考訳であり、正式な効力を持つのは冒頭の英語原文（MIT License）です。"""


class OreHighlighterWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"鉱石視認性向上ツール　OreHighlighter（v{APP_VERSION}）")
        # 1920×1080でも周囲に余裕を持って表示されるデフォルトサイズ。
        # 以前は各タブ（特にGUIアイコン編集タブ）の中身がQScrollAreaに
        # 収まっておらず、その最小サイズがウィンドウ全体に伝播してこの指定を
        # 上書きしてしまっていたが、各タブ側の修正によりこの指定が正しく効くようになった。
        self.resize(1300, 760)
        self.setAcceptDrops(True)

        icon_path = resource_path("icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self._build_ui()
        self._auto_load_config()
        self._update_generate_summary()

        self._update_banner = None
        if ENABLE_UPDATE_CHECK:
            self._check_for_updates()

    def _build_ui(self):
        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        self._central_layout = central_layout  # 更新案内バナーをinsertWidget(0, ...)で差し込むために保持

        warning_banner = QLabel(
            "このツールで作ったリソースパックは、他のPCでもこのツールがあれば簡単に編集できます。\n"
            "⚠ ここで加工したアイテムは、自分の画面でしか見えません。マルチプレイなどで他のプレイヤーから見ると、"
            "標準（オリジナル）のテクスチャのまま表示されます。同じリソパを使用した場合のみ共有できます。"
        )
        warning_banner.setStyleSheet(
            "color: #c0392b; font-size: 15px; font-weight: bold;"
            "padding: 8px 12px;"
        )
        warning_banner.setWordWrap(True)
        central_layout.addWidget(warning_banner)

        self.generate_summary_label = QLabel("生成予定: (未計算)")
        self.generate_summary_label.setStyleSheet(
            "font-size: 12px; color: #2f77d8; font-weight: bold; padding: 4px 12px 0;"
        )
        self.generate_summary_label.setWordWrap(True)
        central_layout.addWidget(self.generate_summary_label)

        header_btn_row = QHBoxLayout()
        header_btn_row.setContentsMargins(12, 4, 12, 8)
        header_btn_row.setSpacing(10)
        save_cfg_btn = QPushButton("設定を保存")
        save_cfg_btn.clicked.connect(self.on_save_config)
        load_cfg_btn = QPushButton("設定を読み込み")
        load_cfg_btn.clicked.connect(self.on_load_config)
        generate_btn = QPushButton("リソースパックを生成")
        generate_btn.setStyleSheet("font-weight: bold;")
        generate_btn.clicked.connect(self.on_generate)
        quit_btn = QPushButton("終了")
        quit_btn.clicked.connect(self.close)

        # 4つとも同じ幅に揃える（一番長いテキストが収まる幅を基準にする）
        header_buttons = [save_cfg_btn, load_cfg_btn, generate_btn, quit_btn]
        widest = max(btn.fontMetrics().horizontalAdvance(btn.text()) for btn in header_buttons)
        uniform_width = widest + 40  # 左右の余白分
        for btn in header_buttons:
            btn.setMinimumWidth(uniform_width)
            header_btn_row.addWidget(btn)
        header_btn_row.addStretch(1)
        central_layout.addLayout(header_btn_row)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabBar::tab {
                background: #e4e6ea;
                color: #444;
                padding: 8px 18px;
                margin-right: 2px;
                border: 1px solid #c7cbd1;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background: white;
                color: #1c4a86;
                font-weight: bold;
                border: 2px solid #2f77d8;
                border-bottom: none;
            }
            QTabBar::tab:!selected:hover {
                background: #d3d7dc;
            }
            QTabWidget::pane {
                border: 1px solid #c7cbd1;
            }
        """)
        central_layout.addWidget(self.tabs)
        self.setCentralWidget(central)

        self.block_tab = BlockEffectTab(app_version=APP_VERSION, resource_path=resource_path)

        # 読み込み系の操作（jar/フォルダ/ランチャー検出/既存プロジェクト/既存パック）は
        # 「読み込み」タブに集約した。作業の起点なので先頭に置く。
        # 中身は block_tab / gui_icon_tab が持つウィジェットを並べ直したもので、
        # SourceImportTab 自体は状態を持たない（source_tab.py の説明を参照）。
        self.source_tab = SourceImportTab()
        self.tabs.addTab(self.source_tab, "読み込み")

        # パック名・出力先・パックアイコン等の「出力設定」は、以前はブロック
        # エフェクトタブの右側パネルに同居していたが、見つけやすさのため
        # 独立したタブに分離した。データ自体は引き続きblock_tabが保持する。
        # 「読み込み → 出力設定」と、パックの入口と出口を先頭2つに並べている。
        self.tabs.addTab(self.block_tab.output_settings_tab, "出力設定")

        self.tabs.addTab(self.block_tab, "ブロックエフェクト")

        self.gui_icon_tab = GuiIconEditorTab()
        self.gui_icon_tab.get_pack_output_info = self.block_tab.get_pack_output_info
        self.gui_icon_tab.get_source_dir_hint = self.block_tab.get_source_dir_hint
        self.gui_icon_tab.get_project_dir_hint = self.block_tab.get_project_dir_hint
        self.tabs.addTab(self.gui_icon_tab, "GUIアイコン編集（体力・満腹度）")

        self.item_tab = ItemTextureEditorTab()
        self.tabs.addTab(self.item_tab, "アイテムテクスチャ編集")

        # ブロックタブはパック生成の起点なので、他タブと共通処理をここで注入する
        self.block_tab.bind_host(
            gui_icon_tab=self.gui_icon_tab,
            item_tab=self.item_tab,
            show_busy_dialog=self._show_busy_dialog,
            close_busy_dialog=self._close_busy_dialog,
            notify_summary_changed=self._update_generate_summary,
        )

        # 「読み込み」タブに、他タブが作った読み込み用ウィジェットを並べる。
        # 全タブ生成後に一度だけ呼ぶこと。
        self.source_tab.bind_tabs(self.block_tab, self.gui_icon_tab)

        self.tabs.addTab(self._build_about_tab(), "その他")

        self._prev_tab_index = self.tabs.currentIndex()
        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _build_about_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(10)

        title = QLabel(APP_NAME)
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        version_label = QLabel(f"バージョン: {APP_VERSION}")
        layout.addWidget(version_label)

        copyright_label = QLabel(APP_COPYRIGHT)
        layout.addWidget(copyright_label)

        manual_btn = QPushButton("使用マニュアルを開く（ブラウザで表示）")
        manual_btn.setToolTip(f"同じフォルダにある「{MANUAL_HTML_FILENAME}」をブラウザで開きます")
        manual_btn.clicked.connect(self._on_open_manual)
        layout.addWidget(manual_btn)

        license_title = QLabel("ライセンス（MIT License）")
        license_title.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(license_title)

        license_note = QLabel(
            "改変・商用利用・再配布は自由です。ただし著作権表示（Copyright）は削除しないでください。"
        )
        license_note.setWordWrap(True)
        layout.addWidget(license_note)

        license_text = QTextEdit()
        license_text.setReadOnly(True)
        license_text.setPlainText(MIT_LICENSE_EN + "\n\n" + "-" * 60 + "\n\n" + MIT_LICENSE_JA)
        layout.addWidget(license_text, 1)

        # 他タブと同様、ボタンが押し縮められて文字が欠けないようにする（共通対策）。
        fix_button_widths(tab)

        return tab

    def _on_open_manual(self):
        manual_path = os.path.join(APP_DIR, MANUAL_HTML_FILENAME)
        if not os.path.exists(manual_path):
            QMessageBox.warning(
                self, "見つかりません",
                f"使用マニュアルが見つかりませんでした。\n「{MANUAL_HTML_FILENAME}」を"
                f"main.pyと同じフォルダに置いてください。"
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(manual_path))

    def _on_tab_changed(self, index):
        # GUIアイコン編集タブから離れるとき、未保存の変更があれば確認する
        gui_tab_index = self.tabs.indexOf(self.gui_icon_tab)
        if self._prev_tab_index == gui_tab_index and index != gui_tab_index:
            if not self.gui_icon_tab.confirm_discard_if_dirty(self):
                self.tabs.blockSignals(True)
                self.tabs.setCurrentIndex(self._prev_tab_index)
                self.tabs.blockSignals(False)
                return
        self._prev_tab_index = self.tabs.currentIndex()
        self._update_generate_summary()

    def _show_busy_dialog(self, message="反映中..."):
        """
        時間のかかる処理（jarの展開など）の間、ユーザーに「処理中」だと分かるよう
        表示する簡易ウィンドウ。ボタンは無く、処理が終わったら呼び出し側でcloseする。
        表示直後にprocessEvents()で強制的に描画するので、そのまま重い処理をしても
        画面が真っ白のまま固まって見えることはない。

        QDialogのモーダル（setModal(True)）は使わない。close()した後もQtの内部的な
        モーダル状態が残り、以降の処理が固まることがあったため、代わりにメイン
        ウィンドウ全体を setEnabled(False) で操作不能にすることで同じ効果を得ている。
        """
        dlg = QDialog(self)
        dlg.setWindowTitle("しばらくお待ちください")
        dlg.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel(message)
        label.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #1c4a86;"
            "background: white; padding: 24px 32px; border: 2px solid #2f77d8; border-radius: 6px;"
        )
        layout.addWidget(label)
        dlg.adjustSize()
        # 親ウィンドウの中央に表示する
        parent_geo = self.geometry()
        dlg.move(
            parent_geo.center().x() - dlg.width() // 2,
            parent_geo.center().y() - dlg.height() // 2,
        )
        self.setEnabled(False)
        dlg.show()
        QApplication.processEvents()
        return dlg

    def _close_busy_dialog(self, dlg):
        if dlg is not None:
            dlg.close()
        self.setEnabled(True)
        QApplication.processEvents()

    # ---- 起動時のバージョン更新確認 ----
    def _check_for_updates(self):
        """GitHub Releasesの最新版を非同期に確認する。
        失敗しても例外を外に投げない（オフライン・GitHub側の問題等は無視する）。"""
        try:
            self._update_manager = QNetworkAccessManager(self)
            request = QNetworkRequest(QUrl(GITHUB_RELEASES_API_URL))
            # GitHub APIはUser-Agentが無いリクエストを拒否するため必須。
            request.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader, "OreHighlighter-UpdateCheck")
            reply = self._update_manager.get(request)
            reply.finished.connect(lambda: self._on_update_check_finished(reply))
        except Exception:
            pass

    def _on_update_check_finished(self, reply):
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                return
            data = bytes(reply.readAll())
            info = json.loads(data.decode("utf-8"))
            latest_version = info.get("tag_name") or info.get("name")
            release_url = info.get("html_url") or GITHUB_RELEASES_PAGE_URL
            if latest_version and is_newer_version(latest_version, APP_VERSION):
                self._show_update_banner(latest_version, release_url)
        except Exception:
            pass
        finally:
            reply.deleteLater()

    def _show_update_banner(self, latest_version, release_url):
        if self._update_banner is not None:
            return  # 二重表示を防ぐ
        banner = QWidget()
        banner.setStyleSheet("background: #fff4d6; border-bottom: 1px solid #e0c56a;")
        row = QHBoxLayout(banner)
        row.setContentsMargins(12, 6, 12, 6)
        label = QLabel(
            f"新しいバージョン {latest_version} が公開されています（現在: v{APP_VERSION}）。"
        )
        label.setStyleSheet("color: #6b5300; font-weight: bold;")
        row.addWidget(label)
        row.addStretch(1)
        open_btn = QPushButton("ダウンロードページを開く")
        open_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(release_url)))
        row.addWidget(open_btn)
        close_btn = QPushButton("×")
        close_btn.setFixedWidth(28)
        close_btn.clicked.connect(self._dismiss_update_banner)
        row.addWidget(close_btn)
        self._central_layout.insertWidget(0, banner)
        self._update_banner = banner

    def _dismiss_update_banner(self):
        if self._update_banner is not None:
            self._update_banner.setParent(None)
            self._update_banner.deleteLater()
            self._update_banner = None

    def _update_generate_summary(self):
        block_count = self.block_tab.get_target_count()
        gui_count = self.gui_icon_tab.get_filled_count()
        item_count = self.item_tab.get_filled_count()
        total = block_count + gui_count + item_count
        if total == 0:
            self.generate_summary_label.setText(
                "生成予定: まだ何も対象がありません（対象ブロック・GUIアイコン・アイテムのいずれかを設定してください）"
            )
        else:
            self.generate_summary_label.setText(
                f"生成予定: ブロック{block_count}件・GUIアイコン{gui_count}件・アイテムテクスチャ{item_count}件"
            )


    # ---------------------------------------------------------------
    # ドラッグ&ドロップ対応（アクティブなタブと拡張子で振り分ける）
    # ---------------------------------------------------------------
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if not urls:
            return
        path = urls[0].toLocalFile()
        if not path or not os.path.exists(path):
            return

        current_tab = self.tabs.currentWidget()

        if os.path.isdir(path):
            if current_tab is self.gui_icon_tab:
                self.gui_icon_tab._start_pack_import(path)
            else:
                self.block_tab.load_textures_folder(path)
                self.block_tab.set_status(f"ドラッグ&ドロップでフォルダを読み込みました: {path}")
            event.acceptProposedAction()
            return

        ext = os.path.splitext(path)[1].lower()

        if ext == ".jar":
            self.block_tab.load_jar(path)
            event.acceptProposedAction()
            return

        if ext == ".zip":
            try:
                extract_dir = tempfile.mkdtemp(prefix="ore_highlighter_drop_")
                with zipfile.ZipFile(path, "r") as z:
                    z.extractall(extract_dir)
            except zipfile.BadZipFile:
                QMessageBox.critical(self, "エラー", "zipファイルとして読み込めませんでした。")
                return
            except Exception as e:
                QMessageBox.critical(self, "エラー", f"読み込みに失敗しました: {e}")
                return
            if current_tab is self.gui_icon_tab:
                self.gui_icon_tab._start_pack_import(extract_dir)
            elif current_tab in (self.block_tab, self.source_tab):
                # 「読み込み」タブは既存プロジェクトを開く導線を持つので、
                # ブロックエフェクトタブと同じ扱いにする。
                self.block_tab.import_project(extract_dir)
            else:
                QMessageBox.information(
                    self, "インポート",
                    "zipファイルの読み込みは「読み込み」「ブロックエフェクト」または\n"
                    "「GUIアイコン編集」タブでドラッグ&ドロップしてください。"
                )
            event.acceptProposedAction()
            return

        if ext in (".png", ".jpg", ".jpeg", ".bmp", ".gif"):
            if current_tab is self.gui_icon_tab:
                if self.gui_icon_tab._current_variant is None:
                    QMessageBox.information(
                        self, "インポート", "先にGUIアイコン編集タブでバリアントを選んでください。"
                    )
                else:
                    self.gui_icon_tab.import_png_path(path)
            elif current_tab is self.item_tab:
                if self.item_tab._current_filename is None:
                    QMessageBox.information(
                        self, "インポート",
                        "先にアイテムテクスチャ編集タブで対象アイテムを1件選んでください。"
                    )
                else:
                    self.item_tab.import_image_path(path)
            else:
                QMessageBox.information(
                    self, "インポート",
                    "画像ファイルは「GUIアイコン編集」または「アイテムテクスチャ編集」タブで、\n"
                    "対象を選んだ状態でドラッグ&ドロップしてください。"
                )
            event.acceptProposedAction()
            return


    # ---------------------------------------------------------------
    # 設定（config.json）の保存・読み込み
    # ---------------------------------------------------------------
    def on_generate(self):
        self.block_tab.on_generate()

    def _current_config(self):
        # ブロックタブ側のキー（textures_dir / output_dir / target_blocks /
        # pack_name / pack_desc / pack_icon_path）はトップレベルのまま維持する。
        cfg = dict(self.block_tab.serialize())
        cfg.update({
            "gui_icons": self.gui_icon_tab.serialize(),
            "gui_icon_reference_dir": self.gui_icon_tab.reference_dir,
            "item_textures": self.item_tab.serialize(),
        })
        return cfg

    def _save_config_to_path(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._current_config(), f, indent=2, ensure_ascii=False)

    def _apply_config(self, cfg):
        # 順序に意味がある: ブロックタブが textures_dir を確定させる過程で
        # アイテムタブの items_dir も設定されるため、必ずブロック → GUI → アイテムの順。
        self.block_tab.deserialize(cfg)

        self.gui_icon_tab.deserialize(cfg.get("gui_icons", {}))

        ref_dir = cfg.get("gui_icon_reference_dir")
        if ref_dir and os.path.isdir(ref_dir):
            self.gui_icon_tab.set_reference_dir(ref_dir)

        self.item_tab.deserialize(cfg.get("item_textures", {}))

    def _load_config_from_path(self, path):
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        self._apply_config(cfg)

    def _migrate_legacy_auto_config_if_needed(self):
        """
        新しい保存先（AUTO_CONFIG_PATH、OS標準のユーザーデータ置き場）にまだ
        設定が無く、旧バージョンの保存先（LEGACY_AUTO_CONFIG_PATH、exe本体と
        同じフォルダ）にだけ設定が残っている場合、一度だけ新しい場所へコピーする。
        これにより、v2.1.3より前から使っている人がバージョンアップしても、
        今回引き継いだこの1回だけは既存の設定が失われない。
        """
        if os.path.exists(AUTO_CONFIG_PATH):
            return  # 既に新しい場所に設定がある（移行済み、または新規に保存済み）
        if not os.path.exists(LEGACY_AUTO_CONFIG_PATH):
            return  # 旧い場所にも何も無い（新規インストール）
        try:
            os.makedirs(os.path.dirname(AUTO_CONFIG_PATH), exist_ok=True)
            shutil.copyfile(LEGACY_AUTO_CONFIG_PATH, AUTO_CONFIG_PATH)
        except Exception:
            pass

    def _auto_load_config(self):
        self._migrate_legacy_auto_config_if_needed()
        if os.path.exists(AUTO_CONFIG_PATH):
            try:
                self._load_config_from_path(AUTO_CONFIG_PATH)
                self.block_tab.set_status("前回の設定を自動的に読み込みました")
            except Exception:
                pass

    def closeEvent(self, event):
        if not self.gui_icon_tab.confirm_discard_if_dirty(self):
            event.ignore()
            return
        try:
            os.makedirs(os.path.dirname(AUTO_CONFIG_PATH), exist_ok=True)
            self._save_config_to_path(AUTO_CONFIG_PATH)
        except Exception:
            pass
        event.accept()

    def on_save_config(self):
        path, _ = QFileDialog.getSaveFileName(self, "設定を保存", CONFIG_DEFAULT_NAME, "JSON (*.json)")
        if not path:
            return
        self._save_config_to_path(path)
        self.block_tab.set_status(f"設定を保存しました: {path}")

    def on_load_config(self):
        path, _ = QFileDialog.getOpenFileName(self, "設定を読み込み", "", "JSON (*.json)")
        if not path:
            return
        try:
            self._load_config_from_path(path)
        except Exception as e:
            QMessageBox.warning(self, "エラー", f"読み込みに失敗しました: {e}")
            return
        self.block_tab.set_status(f"設定を読み込みました: {path}")



BUTTON_STYLESHEET = """
QPushButton {
    background-color: #2f77d8;
    color: white;
    border: 1px solid #1f5aa8;
    border-radius: 4px;
    padding: 6px 14px;
}
QPushButton:hover {
    background-color: #4a90e2;
    border: 1px solid #2f6fc4;
}
QPushButton:pressed {
    background-color: #1c4a86;
    border: 1px solid #123561;
}
QPushButton:checked {
    background-color: #123561;
    border: 2px solid #ffd54a;
}
QPushButton:disabled {
    background-color: #b6bfc9;
    color: #7c8794;
    border: 1px solid #9aa4b0;
}
""" + SCROLLBAR_QSS
# スクロールバー（太く・つまみを大きく）は全タブ・全ダイアログに共通で
# 効かせたいので、アプリ全体のスタイルシート（app.setStyleSheet）に
# 連結している。ui_utils.SCROLLBAR_QSS を参照。


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(BUTTON_STYLESHEET)
    icon_path = resource_path("icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    window = OreHighlighterWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()