"""
リソースパック生成のテスト（正常系）。

v1.2.0以降のルール:
  - 出力は必ずzip。フォルダのまま残してはいけない
  - oreHighlighterProject.json にローカルパスを含めない
"""

import json
import os
import tempfile
import unittest
import zipfile

from helpers import (  # noqa: F401
    make_ready_window, make_window, silence_dialogs,
)
import effect_catalog as EC
import main as M


class TestPackGeneration(unittest.TestCase):
    def setUp(self):
        silence_dialogs()
        self.window, self.bt, self.tmp, self.block_dir, self.out = make_ready_window("TestPack")

    def _generate(self):
        self.window.on_generate()  # ヘッダーボタン経路（main → block_tab への委譲も検証）
        return os.path.join(self.out, "TestPack.zip")

    def test_outputs_zip_and_removes_folder(self):
        zip_path = self._generate()
        self.assertTrue(os.path.isfile(zip_path), f"zipが無い: {os.listdir(self.out)}")
        self.assertFalse(
            os.path.isdir(os.path.join(self.out, "TestPack")),
            "パックフォルダが残っている（v1.2.0以降はzipのみ）",
        )
        self.assertEqual(os.listdir(self.out), ["TestPack.zip"])

    def test_zip_contains_expected_files(self):
        with zipfile.ZipFile(self._generate()) as z:
            self.assertIsNone(z.testzip(), "zipが壊れている")
            names = [n.replace("\\", "/") for n in z.namelist()]

        self.assertIn("pack.mcmeta", names)
        self.assertIn("pack.png", names)
        self.assertIn("oreHighlighterProject.json", names)

        pngs = [n for n in names
                if n.startswith("assets/minecraft/textures/block/") and n.endswith(".png")]
        self.assertEqual(len(pngs), 3)

    def test_project_json_excludes_local_paths(self):
        """
        配布されたパックを他人が開けるよう、ローカルパス（pathキー）は
        埋め込まない。ここが漏れると個人のフォルダ構成が第三者に渡る。
        """
        with zipfile.ZipFile(self._generate()) as z:
            project = json.loads(z.read("oreHighlighterProject.json").decode("utf-8"))

        for block in project["target_blocks"]:
            self.assertNotIn("path", block, "oreHighlighterProject.json にローカルパスが混入")
        self.assertEqual(project["generated_by"], f"OreHighlighter v{M.APP_VERSION}")

    def test_pack_mcmeta_is_valid_json(self):
        self.bt.pack_desc_edit.setText("テスト用の説明文")
        with zipfile.ZipFile(self._generate()) as z:
            mcmeta = json.loads(z.read("pack.mcmeta").decode("utf-8"))
        self.assertEqual(mcmeta["pack"]["description"], "テスト用の説明文")

    def test_project_import_round_trip(self):
        """生成したパックを読み込み直して、エフェクト設定が復元できること。"""
        self.bt.target_list.setCurrentRow(0)
        self.bt.effect_combo.setCurrentText("点滅")
        zip_path = self._generate()

        extract_dir = tempfile.mkdtemp(prefix="ore_test_import_")
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(extract_dir)

        other = make_window()
        other.block_tab.load_textures_folder(self.block_dir)
        other.block_tab.import_project(extract_dir)

        self.assertEqual(len(other.block_tab.target_blocks), 3)
        self.assertEqual(other.block_tab.target_blocks[0]["effect"], EC.BLINK)
        self.assertTrue(
            os.path.exists(other.block_tab.target_blocks[0]["path"]),
            "pathが受け取り側で解決されていない",
        )

    def test_generate_without_output_dir_does_nothing(self):
        self.bt.output_dir = None
        self.window.on_generate()
        self.assertEqual(os.listdir(self.out), [])


if __name__ == "__main__":
    unittest.main()
