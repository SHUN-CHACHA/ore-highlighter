"""
テスト共通のヘルパー。

【重要】このモジュールは PyQt6 より先に import すること。
QT_QPA_PLATFORM=offscreen を import 時に設定するため、順序が逆だと
画面の無い環境（CI・SSH接続先など）でテストが起動できなくなる。

    from helpers import ...   # ← 必ず先頭
    from PyQt6.QtWidgets import ...

Copyright (c) 2026 旬茶
Licensed under the MIT License.
"""

import os
import sys
import tempfile
import zipfile

# --- PyQt6 より前に実行する必要がある設定 ---
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# tests/ の親（ソースルート）を import パスに追加する
SOURCE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SOURCE_ROOT not in sys.path:
    sys.path.insert(0, SOURCE_ROOT)

from PyQt6.QtWidgets import QApplication, QMessageBox  # noqa: E402
from PyQt6.QtCore import QMimeData, QUrl, QPointF, Qt  # noqa: E402
from PyQt6.QtGui import QDropEvent  # noqa: E402

import main as M  # noqa: E402
from texture_effects import create_placeholder_ore_texture  # noqa: E402

# 起動時のバージョン更新確認（GitHubへの実際のネットワークアクセスを伴う）は、
# テスト環境では常に無効化しておく。個別にこの機能自体をテストしたい場合
# （test_update_check.py）は、そのテスト内で明示的にTrueへ戻してから使う。
M.ENABLE_UPDATE_CHECK = False

_app = None


def get_app():
    """QApplication はプロセスに1つだけ。テストモジュールを跨いで使い回す。"""
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


# ---------------------------------------------------------------
# ダイアログの無効化
# ---------------------------------------------------------------
def silence_dialogs(answer=QMessageBox.StandardButton.Yes):
    """
    QMessageBox の静的メソッドを差し替えて、テスト中にダイアログで止まらないようにする。
    戻り値は critical に渡されたメッセージを溜めるリスト（エラー文言の検証用）。

    【注意】静的メソッド（question / information / warning / critical）を潰しても、
    box.exec() を使う実装（_ask_project_import_mode など）は止められない。
    そちらを通るテストでは silence_exec() も併用すること。
    """
    criticals = []
    QMessageBox.question = staticmethod(lambda *a, **k: answer)
    QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    QMessageBox.critical = staticmethod(
        lambda parent, title, text, *a, **k: criticals.append(text)
    )
    return criticals


def silence_exec(result=QMessageBox.StandardButton.Discard):
    """box.exec() を使うダイアログ（未保存確認・読み込み方法の選択など）を潰す。"""
    QMessageBox.exec = lambda self: result


# ---------------------------------------------------------------
# テスト用のダミー素材
# ---------------------------------------------------------------
def make_texture_folder(names=("diamond_ore.png", "iron_ore.png", "gold_ore.png")):
    """
    展開済みの .../textures/block 相当のフォルダを作り、(tmp_root, block_dir, item_dir) を返す。

    【注意】ダミー画像に1バイトの偽PNG（b"x"）を使うとPILの挙動が不安定になるため、
    必ず create_placeholder_ore_texture() で本物のPNGを作ること。
    """
    tmp = tempfile.mkdtemp(prefix="ore_test_")
    block_dir = os.path.join(tmp, "assets", "minecraft", "textures", "block")
    item_dir = os.path.join(tmp, "assets", "minecraft", "textures", "item")
    os.makedirs(block_dir)
    os.makedirs(item_dir)
    for n in names:
        create_placeholder_ore_texture().save(os.path.join(block_dir, n))
    create_placeholder_ore_texture().save(os.path.join(item_dir, "diamond_pickaxe.png"))
    return tmp, block_dir, item_dir


def make_jar(tmp_root, block_names=("diamond_ore.png", "iron_ore.png")):
    """block / gui hud / item を含む、本物のjar（zip）を作って그パスを返す。"""
    jar_path = os.path.join(tmp_root, "26.2.jar")
    png = os.path.join(tmp_root, "_src.png")
    create_placeholder_ore_texture().save(png)
    with zipfile.ZipFile(jar_path, "w") as z:
        for n in block_names:
            z.write(png, f"assets/minecraft/textures/block/{n}")
        z.write(png, "assets/minecraft/textures/gui/sprites/hud/heart/full.png")
        z.write(png, "assets/minecraft/textures/item/diamond_pickaxe.png")
    return jar_path


def make_output_dir(tmp_root, name="resourcepacks"):
    out = os.path.join(tmp_root, name)
    os.makedirs(out, exist_ok=True)
    return out


# ---------------------------------------------------------------
# ウィンドウの生成
# ---------------------------------------------------------------
def make_window():
    """
    テスト用の OreHighlighterWindow を作る。

    【重要】main.AUTO_CONFIG_PATH と main.LEGACY_AUTO_CONFIG_PATH を、
    どちらも存在しない一時パスへ向け直してから生成する。
    そうしないと _auto_load_config() が「開発中の本物の config.json」を
    読み込んだり、旧保存先からの自動移行が働いたりして、
    テスト結果が手元の環境に依存してしまう。
    """
    get_app()
    M.AUTO_CONFIG_PATH = os.path.join(
        tempfile.mkdtemp(prefix="ore_test_cfg_"), "config.json"
    )
    M.LEGACY_AUTO_CONFIG_PATH = os.path.join(
        tempfile.mkdtemp(prefix="ore_test_cfg_legacy_"), "config.json"
    )
    return M.OreHighlighterWindow()


def make_ready_window(pack_name="TestPack"):
    """
    「テクスチャ読み込み済み・対象ブロック追加済み・出力先設定済み」の状態まで
    進めたウィンドウを返す。戻り値: (window, block_tab, tmp_root, block_dir, output_dir)
    """
    tmp, block_dir, _item_dir = make_texture_folder()
    out = make_output_dir(tmp)
    w = make_window()
    bt = w.block_tab
    bt.load_textures_folder(block_dir)
    bt.browse_list.selectAll()
    bt.on_add_to_targets()
    bt.output_dir = out
    bt.pack_name_edit.setText(pack_name)
    return w, bt, tmp, block_dir, out


# ---------------------------------------------------------------
# ドラッグ&ドロップ
# ---------------------------------------------------------------
def drop_on(window, path, tab):
    """
    実際の QDropEvent を組み立ててウィンドウに投げる。
    メソッドを直接呼ぶのではなく本物のイベントを使うことで、
    タブごとの振り分けロジックまで通して検証できる。
    戻り値: イベントが受理されたか。
    """
    window.tabs.setCurrentWidget(tab)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(path)])
    event = QDropEvent(
        QPointF(1, 1),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    window.dropEvent(event)
    return event.isAccepted()


def raiser(message="テスト用の想定外エラー", exc=RuntimeError):
    """export_all などを差し替えて、失敗ケースを再現するための関数を返す。"""
    def _boom(*_args, **_kwargs):
        raise exc(message)
    return _boom
