"""
2点の修正のテスト:

1. 既存のOreHighlighterプロジェクト（フォルダ／zip）を開いたとき、次回の
   「リソースパックを生成」がその場所を上書きするよう、出力先・パック名を
   自動で引き継ぐこと。
2. 「リソースパックを生成」時、出力先に同名のパックが既にある場合は
   Windowsのファイル置き換え確認と同じ考え方で上書き可否を確認すること。
   確認せず黙って上書きしていたのが元の問題。
"""

import os
import tempfile
import unittest
import zipfile

from helpers import make_ready_window, make_window, silence_dialogs  # noqa: F401
import effect_catalog as EC
from PyQt6.QtWidgets import QMessageBox


class TestProjectOpenInheritsOutputDir(unittest.TestCase):
    def setUp(self):
        silence_dialogs()
        self.window, self.bt, self.tmp, self.block_dir, self.out = make_ready_window("TestPack")
        self.window.on_generate()
        self.zip_path = os.path.join(self.out, "TestPack.zip")
        self.assertTrue(os.path.isfile(self.zip_path))

    def test_opening_extracted_folder_sets_output_dir_to_parent_and_pack_name_to_folder(self):
        pack_folder = os.path.join(self.tmp, "SomeExtractedPack")
        os.makedirs(pack_folder)
        with zipfile.ZipFile(self.zip_path) as z:
            z.extractall(pack_folder)

        other = make_window()
        other.block_tab.load_textures_folder(self.block_dir)
        other.block_tab._start_project_import(pack_folder, origin_kind="folder", origin_path=pack_folder)

        self.assertEqual(other.block_tab.output_dir, self.tmp)
        self.assertEqual(other.block_tab.pack_name_edit.text(), "SomeExtractedPack")
        self.assertEqual(other.block_tab.output_dir_label.text(), self.tmp)

    def test_opening_zip_sets_output_dir_to_zips_folder_and_pack_name_to_zip_filename(self):
        extract_dir = tempfile.mkdtemp(prefix="ore_test_zip_extract_")
        with zipfile.ZipFile(self.zip_path) as z:
            z.extractall(extract_dir)

        other = make_window()
        other.block_tab.load_textures_folder(self.block_dir)
        # on_import_project_zip() が展開後にやるのと同じ呼び方
        # （展開先の一時フォルダではなく、元のzip自体の場所を引き継ぎ元にする）
        other.block_tab._start_project_import(extract_dir, origin_kind="zip", origin_path=self.zip_path)

        self.assertEqual(other.block_tab.output_dir, self.out)
        self.assertEqual(other.block_tab.pack_name_edit.text(), "TestPack")

    def test_merge_into_existing_session_still_switches_output_dir(self):
        """
        「開く」＝そのプロジェクトを続けて編集したい、という意図のはずなので、
        既に何か対象がある状態でマージ読み込みしても出力先は切り替わること。
        """
        pack_folder = os.path.join(self.tmp, "OtherPack")
        os.makedirs(pack_folder)
        with zipfile.ZipFile(self.zip_path) as z:
            z.extractall(pack_folder)

        other = make_window()
        other.block_tab.load_textures_folder(self.block_dir)
        other.block_tab.output_dir = "/some/unrelated/old/output"
        other.block_tab.pack_name_edit.setText("OldName")
        other.block_tab.browse_list.selectAll()
        other.block_tab.on_add_to_targets()  # 既存の対象がある状態を作る

        # 対象が既にある状態での読み込みは _ask_project_import_mode() が
        # box.exec() の本物のモーダルを開くため、画面の無いテスト環境では
        # ここを直接差し替えて回避する（他のテストファイルと同じパターン）。
        other.block_tab._ask_project_import_mode = lambda: "merge"
        other.block_tab._start_project_import(pack_folder, origin_kind="folder", origin_path=pack_folder)

        self.assertEqual(other.block_tab.output_dir, self.tmp)
        self.assertEqual(other.block_tab.pack_name_edit.text(), "OtherPack")


class TestGuiIconTabFollowsOpenedProject(unittest.TestCase):
    """
    GUIアイコンタブの「フォルダから読み込む/zipから読み込む」の初期位置が、
    直近で開いたOreHighlighterプロジェクトの場所に揃うことの確認。
    """

    def setUp(self):
        silence_dialogs()
        self.window, self.bt, self.tmp, self.block_dir, self.out = make_ready_window("TestPack")
        self.window.on_generate()
        self.zip_path = os.path.join(self.out, "TestPack.zip")

    def test_before_opening_any_project_falls_back_to_vanilla_source_hint(self):
        hint = self.window.gui_icon_tab._get_start_dir_hint()
        self.assertEqual(hint, self.bt.get_source_dir_hint())

    def test_after_opening_project_folder_gui_tab_hint_points_there(self):
        pack_folder = os.path.join(self.tmp, "SomeExtractedPack")
        os.makedirs(pack_folder)
        with zipfile.ZipFile(self.zip_path) as z:
            z.extractall(pack_folder)

        # setUpのmake_ready_windowで既に対象ブロックが3件入っている状態なので、
        # _ask_project_import_mode() の本物のモーダルを避けるため直接差し替える。
        self.bt._ask_project_import_mode = lambda: "merge"
        self.bt._start_project_import(pack_folder, origin_kind="folder", origin_path=pack_folder)

        self.assertEqual(self.window.gui_icon_tab._get_start_dir_hint(), pack_folder)

    def test_after_opening_project_zip_gui_tab_hint_points_to_zips_folder(self):
        extract_dir = tempfile.mkdtemp(prefix="ore_test_zip_extract_")
        with zipfile.ZipFile(self.zip_path) as z:
            z.extractall(extract_dir)

        self.bt._ask_project_import_mode = lambda: "merge"
        self.bt._start_project_import(extract_dir, origin_kind="zip", origin_path=self.zip_path)

        self.assertEqual(self.window.gui_icon_tab._get_start_dir_hint(), self.out)


class TestGenerateOverwriteConfirmation(unittest.TestCase):
    def setUp(self):
        self.criticals = silence_dialogs()
        self.window, self.bt, self.tmp, self.block_dir, self.out = make_ready_window("TestPack")
        self.zip_path = os.path.join(self.out, "TestPack.zip")

    def _patch_question(self, answer):
        calls = []

        def fake_question(_self_or_parent, title, text, *a, **k):
            calls.append(title)
            return answer

        QMessageBox.question = staticmethod(fake_question)
        return calls

    def test_first_generation_does_not_ask_to_overwrite(self):
        calls = self._patch_question(QMessageBox.StandardButton.Yes)
        self.window.on_generate()
        self.assertTrue(os.path.isfile(self.zip_path))
        self.assertNotIn("上書きの確認", calls, "既存パックが無いのに確認が出た")

    def test_second_generation_asks_and_declining_keeps_old_zip(self):
        silence_dialogs()  # 1回目はYes系の既定応答で普通に生成させる
        self.window.on_generate()
        self.assertTrue(os.path.isfile(self.zip_path))
        old_mtime = os.path.getmtime(self.zip_path)
        old_size = os.path.getsize(self.zip_path)

        # ブロックを1件追加して内容を変え、2回目の生成で中身が変わることを検出できるようにする
        self.bt.target_list.setCurrentRow(0)
        self.bt.effect_combo.setCurrentText("点滅")

        calls = self._patch_question(QMessageBox.StandardButton.No)
        self.window.on_generate()

        self.assertIn("上書きの確認", calls, "2回目の生成で上書き確認が出ていない")
        self.assertEqual(os.path.getmtime(self.zip_path), old_mtime, "「いいえ」を選んだのに上書きされている")
        self.assertEqual(os.path.getsize(self.zip_path), old_size)

    def test_second_generation_accepting_overwrites(self):
        silence_dialogs()
        self.window.on_generate()
        self.assertTrue(os.path.isfile(self.zip_path))

        self.bt.target_list.setCurrentRow(0)
        self.bt.effect_combo.setCurrentText("点滅")

        calls = self._patch_question(QMessageBox.StandardButton.Yes)
        self.window.on_generate()

        self.assertIn("上書きの確認", calls)
        with zipfile.ZipFile(self.zip_path) as z:
            import json
            project = json.loads(z.read("oreHighlighterProject.json").decode("utf-8"))
        self.assertEqual(project["target_blocks"][0]["effect"], EC.BLINK, "「はい」を選んだのに新しい内容で上書きされていない")


if __name__ == "__main__":
    unittest.main()
