"""
main.py（ホスト）と block_tab.py の結合部分のテスト。

BlockEffectTab は独立したQWidgetだが、パック生成の起点として
他タブ・ビジーダイアログ・サマリー更新を bind_host() で受け取っている。
ここが外れると「起動はするのに、jarを読むと固まる」「他タブの内容が
パックに入らない」といった分かりにくい壊れ方をする。
"""

import os
import unittest

from helpers import (  # noqa: F401
    make_window, make_ready_window, make_texture_folder, make_jar, silence_dialogs,
)
import block_tab as BT


class TestHostBinding(unittest.TestCase):
    def setUp(self):
        silence_dialogs()
        self.window = make_window()
        self.bt = self.window.block_tab

    def test_bind_host_wires_other_tabs(self):
        self.assertIs(self.bt.gui_icon_tab, self.window.gui_icon_tab)
        self.assertIs(self.bt.item_tab, self.window.item_tab)

    def test_app_version_is_injected(self):
        """循環importを避けるため、APP_VERSIONはコンストラクタ経由で渡している。"""
        import main as M
        self.assertEqual(self.bt.app_version, M.APP_VERSION)

    def test_busy_dialog_hook_round_trip(self):
        """
        重い処理の前後で show/close が対になって呼ばれ、
        最後にウィンドウが操作可能へ戻ること。

        （setModal(True) は使わない方針。close()後もQtの内部状態が残って
        　フリーズしたため、setEnabled(False) 方式に統一している）
        """
        calls = []
        original_show = self.bt.show_busy_dialog
        original_close = self.bt.close_busy_dialog
        self.bt.show_busy_dialog = lambda message="反映中...": (
            calls.append("show"), original_show(message))[1]
        self.bt.close_busy_dialog = lambda dlg: (
            calls.append("close"), original_close(dlg))[1]

        tmp, _block_dir, _item_dir = make_texture_folder()
        self.bt.load_jar(make_jar(tmp))

        self.assertEqual(calls, ["show", "close"])
        self.assertTrue(self.window.isEnabled(), "ビジーダイアログ後もウィンドウが無効のまま")

    def test_summary_hook_updates_header(self):
        tmp, block_dir, _item_dir = make_texture_folder()
        self.bt.load_textures_folder(block_dir)
        self.bt.browse_list.selectAll()
        self.bt.on_add_to_targets()
        self.assertIn("ブロック3件", self.window.generate_summary_label.text())

        self.bt.target_list.setCurrentRow(0)
        self.bt.on_remove_targets()
        self.assertIn("ブロック2件", self.window.generate_summary_label.text())

    def test_gui_icon_tab_callbacks(self):
        """GUIアイコン編集タブが、ブロックタブの出力設定を参照できること。"""
        window, bt, tmp, _block_dir, out = make_ready_window("MyPack")
        self.assertEqual(window.gui_icon_tab.get_pack_output_info(), ("MyPack", out))

    def test_source_dir_hint_detects_prism_instance(self):
        """読み込み元のパスに instances/<名前> が含まれていれば、それを覚えること。"""
        path = os.path.join("C:", os.sep, "Prism", "instances", "MyInst", "minecraft", "x")
        self.bt._update_source_hints(path)
        self.assertEqual(self.bt._last_prism_instance_name_hint, "MyInst")
        self.assertTrue(
            self.window.gui_icon_tab.get_source_dir_hint().endswith(
                os.path.join("instances", "MyInst")
            )
        )

    def test_prism_instance_auto_selected_from_hint(self):
        """
        テクスチャ読み込み元と同じPrismインスタンスが検出されたら、
        自動で選択して出力先まで設定すること。
        """
        tmp, _block_dir, _item_dir = make_texture_folder()
        instance_mc = os.path.join(tmp, "instances", "MyInst", "minecraft")
        os.makedirs(instance_mc)

        original = BT.find_prism_instances
        BT.find_prism_instances = lambda: [("Other", instance_mc), ("MyInst", instance_mc)]
        try:
            self.bt._last_prism_instance_name_hint = "MyInst"
            self.bt._synced_output_pack_root = "既に確認済み扱い"
            self.bt.on_detect_prism_instances()
        finally:
            BT.find_prism_instances = original

        self.assertEqual(self.bt.prism_combo.currentText(), "MyInst")
        self.assertEqual(self.bt.output_dir, os.path.join(instance_mc, "resourcepacks"))

    def test_output_pack_sync_imports_item_textures(self):
        """
        出力先に既存パックがある場合、アイテムテクスチャ編集タブへ同期されること。
        （ビジーダイアログを挟む処理なので、フックが外れると固まる）
        """
        from PIL import Image
        import zipfile

        window, bt, tmp, block_dir, out = make_ready_window("SyncPack")
        window.on_generate()

        pack_dir = os.path.join(out, "SyncPack")
        with zipfile.ZipFile(os.path.join(out, "SyncPack.zip")) as z:
            z.extractall(pack_dir)
        item_dir = os.path.join(pack_dir, "assets", "minecraft", "textures", "item")
        os.makedirs(item_dir, exist_ok=True)
        Image.open(os.path.join(window.item_tab.items_dir, "diamond_pickaxe.png")).save(
            os.path.join(item_dir, "diamond_pickaxe.png")
        )

        bt._synced_output_pack_root = None
        bt._maybe_sync_output_pack()

        self.assertGreaterEqual(window.item_tab.get_filled_count(), 1)
        self.assertTrue(window.isEnabled())


if __name__ == "__main__":
    unittest.main()
