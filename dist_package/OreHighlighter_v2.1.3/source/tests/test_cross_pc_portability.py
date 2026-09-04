"""
v1.2.6 で追加した「配布したパックだけで、別PCでも編集を再開できる」機能のテスト。

背景:
  v1.2.5以前は oreHighlighterProject.json に target_blocks しか埋め込まれておらず、
  パックのzipだけを別PCに持って行っても、GUIアイコン・アイテムテクスチャの設定
  （外部PNG画像やエフェクト）は復元できなかった（config.jsonを別途渡す必要があった）。

  この変更で、_write_pack_contents() が gui_icons / item_textures も
  oreHighlighterProject.json に埋め込むようになり、_start_project_import() が
  その3つをまとめて復元するようになった。

このファイルで確認していること:
  1. 生成したパックのoreHighlighterProject.jsonに3種の設定が全て入っていること
  2. 「別PC」（全く別の一時フォルダ・全く別のwindowインスタンス、元のPCのパスを
     一切参照しない状態）でプロジェクトを開くと、ブロック・GUIアイコン・アイテムの
     設定（外部PNG画像のピクセルデータそのものも含む）が復元されること
  3. 復元した状態から、その別PCでも再度パックを生成できること
  4. 後方互換：v1.2.5以前の（gui_icons/item_texturesキーが無い）パックを読み込んでも
     エラーにならないこと
  5. ブロックが0件でもGUIアイコン/アイテムだけのプロジェクトが読み込めること
  6. マージ/置き換えモードが、GUIアイコン・アイテムにも正しく適用されること
  7. 別PC側に元のアイテム画像が存在しない場合は、静かにスキップされること
     （エラーにならず、他の項目の読み込みは続行する）
"""

import base64
import io
import json
import os
import tempfile
import unittest
import zipfile

from helpers import (  # noqa: F401
    make_window, make_ready_window, make_texture_folder, silence_dialogs,
)
import effect_catalog as EC
from PIL import Image


class TestCrossPCPortability(unittest.TestCase):
    def setUp(self):
        silence_dialogs()

    def test_generated_pack_embeds_all_three_sections(self):
        window, bt, tmp, block_dir, out = make_ready_window("EmbedTest")

        bt.target_list.setCurrentRow(0)
        bt.effect_combo.setCurrentText("枠線")
        bt._current_border_color = "#00ffaa"
        bt._update_border_color_button()
        bt.on_editor_changed()

        window.gui_icon_tab.icons["full"] = Image.new("RGBA", (9, 9), (255, 0, 255, 255))

        item_fn = sorted(os.listdir(window.item_tab.items_dir))[0]
        window.item_tab.target_items.append({
            "filename": item_fn, "path": os.path.join(window.item_tab.items_dir, item_fn),
        })
        cfg = window.item_tab._get_or_create_config(item_fn)
        cfg["custom_image"] = Image.new("RGBA", (16, 16), (10, 200, 10, 255))
        cfg["effect"] = EC.RAINBOW

        window.on_generate()
        with zipfile.ZipFile(os.path.join(out, "EmbedTest.zip")) as z:
            project = json.loads(z.read("oreHighlighterProject.json").decode("utf-8"))

        self.assertEqual(project["format_version"], 4)
        self.assertIn("full", project["gui_icons"])
        self.assertIn(item_fn, project["item_textures"]["item_configs"])
        self.assertNotIn(
            "path", project["item_textures"]["target_items"][0],
            "ローカルの絶対パスがパックに混入している",
        )
        for block in project["target_blocks"]:
            self.assertNotIn("path", block)

    def test_full_cross_pc_round_trip(self):
        """
        PC-Aで生成したパックを、PC-Aの一時フォルダ構成とは無関係な
        「別PC」相当の環境で開き、全ての設定（画像データ込み）が復元されることを確認する。
        """
        # ---- PC-A ----
        window_a, bt_a, tmp_a, block_dir_a, out_a = make_ready_window("CrossPC")

        bt_a.target_list.setCurrentRow(0)
        bt_a.effect_combo.setCurrentText("枠線")
        bt_a._current_border_color = "#00ffaa"
        bt_a._update_border_color_button()
        bt_a.on_editor_changed()

        window_a.gui_icon_tab.icons["full"] = Image.new("RGBA", (9, 9), (255, 0, 255, 255))

        item_files = sorted(f for f in os.listdir(window_a.item_tab.items_dir) if f.lower().endswith(".png"))
        target_fn = item_files[0]
        window_a.item_tab.target_items.append({
            "filename": target_fn, "path": os.path.join(window_a.item_tab.items_dir, target_fn),
        })
        cfg = window_a.item_tab._get_or_create_config(target_fn)
        cfg["custom_image"] = Image.new("RGBA", (16, 16), (10, 200, 10, 255))
        cfg["effect"] = EC.RAINBOW
        cfg["frame_count"] = 8

        window_a.on_generate()
        zip_path = os.path.join(out_a, "CrossPC.zip")
        self.assertTrue(os.path.isfile(zip_path))

        # ---- パックを「別PC」の全く別の場所に展開する ----
        extract_dir = tempfile.mkdtemp(prefix="ore_test_pc_b_extract_")
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(extract_dir)

        # ---- PC-B: PC-Aとは無関係な一時フォルダに、同名のテクスチャを新規に用意する ----
        window_b = make_window()
        block_names = tuple(f for f in os.listdir(block_dir_a) if f.lower().endswith(".png"))
        _tmp_b, block_dir_b, item_dir_b = make_texture_folder(names=block_names)
        for fn in item_files:
            if not os.path.exists(os.path.join(item_dir_b, fn)):
                Image.new("RGBA", (16, 16), (128, 128, 128, 255)).save(os.path.join(item_dir_b, fn))

        window_b.block_tab.load_textures_folder(block_dir_b)
        self.assertEqual(window_b.item_tab.items_dir, item_dir_b)

        # ---- PC-B: プロジェクトを開く ----
        window_b.block_tab.import_project(extract_dir)

        # ブロック
        self.assertEqual(len(window_b.block_tab.target_blocks), len(bt_a.target_blocks))
        restored_block = next(
            b for b in window_b.block_tab.target_blocks if b["effect"] == EC.OUTLINE
        )
        self.assertEqual(restored_block["border_color"], "#00ffaa")

        # GUIアイコン
        self.assertIn("full", window_b.gui_icon_tab.icons)
        self.assertEqual(
            list(window_b.gui_icon_tab.icons["full"].getdata())[0], (255, 0, 255, 255)
        )

        # アイテムテクスチャ（画像データそのものが復元されていること）
        restored_cfg = window_b.item_tab.item_configs.get(target_fn)
        self.assertIsNotNone(restored_cfg)
        self.assertEqual(restored_cfg["effect"], EC.RAINBOW)
        self.assertEqual(restored_cfg["frame_count"], 8)
        restored_img = restored_cfg["custom_image"]
        self.assertIsNotNone(restored_img)
        self.assertEqual(restored_img.size, (16, 16))
        self.assertEqual(list(restored_img.getdata())[0], (10, 200, 10, 255))

        # ---- PC-Bでも、復元した内容から再びパックを生成できること ----
        window_b.block_tab.pack_name_edit.setText("CrossPC")
        out_b = tempfile.mkdtemp(prefix="ore_test_pc_b_out_")
        window_b.block_tab.output_dir = out_b
        window_b.on_generate()
        zip_path_b = os.path.join(out_b, "CrossPC.zip")
        self.assertTrue(os.path.isfile(zip_path_b))
        with zipfile.ZipFile(zip_path_b) as z:
            self.assertIsNone(z.testzip())
            names = [n for n in z.namelist() if n.startswith("assets/minecraft/textures/item/")]
            self.assertTrue(any(target_fn in n for n in names))

    def test_old_pack_without_gui_and_item_sections_still_imports(self):
        """v1.2.5以前に生成されたパック（gui_icons/item_texturesキーが無い）でもエラーにならない。"""
        window, bt, tmp, block_dir, out = make_ready_window("OldFmt")
        old_root = tempfile.mkdtemp(prefix="ore_test_old_")
        old_project = {
            "format_version": 1,
            "generated_by": "OreHighlighter v1.2.4",
            "target_blocks": [{
                "filename": sorted(os.listdir(block_dir))[0], "effect": "レインボーのみ",
                "frame_count": 16, "frametime": 2, "thickness": 1,
                "border_saturation": 0.7, "border_brightness": 0.7, "dark_factor": 0.35,
            }],
        }
        with open(os.path.join(old_root, "oreHighlighterProject.json"), "w", encoding="utf-8") as f:
            json.dump(old_project, f, ensure_ascii=False)

        other = make_window()
        other.block_tab.load_textures_folder(block_dir)
        other.block_tab.import_project(old_root)

        self.assertEqual(len(other.block_tab.target_blocks), 1)
        self.assertEqual(other.gui_icon_tab.icons, {})
        self.assertEqual(other.item_tab.item_configs, {})

    def test_zero_blocks_with_gui_icons_only_still_imports(self):
        """ブロックが1件も無いプロジェクトでも、GUIアイコン等があれば読み込みが継続すること。"""
        window, bt, tmp, block_dir, out = make_ready_window("GuiOnly")
        root = tempfile.mkdtemp(prefix="ore_test_guionly_")
        img = Image.new("RGBA", (9, 9), (10, 20, 30, 255))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        project = {
            "format_version": 2, "generated_by": "x",
            "target_blocks": [],
            "gui_icons": {"full": base64.b64encode(buf.getvalue()).decode("ascii")},
            "item_textures": {"target_items": [], "item_configs": {}},
        }
        with open(os.path.join(root, "oreHighlighterProject.json"), "w", encoding="utf-8") as f:
            json.dump(project, f, ensure_ascii=False)

        other = make_window()
        other.block_tab.load_textures_folder(block_dir)
        other.block_tab.import_project(root)

        self.assertEqual(len(other.block_tab.target_blocks), 0)
        self.assertIn("full", other.gui_icon_tab.icons)

    def test_merge_mode_preserves_untouched_gui_icons_and_items(self):
        window, bt, tmp, block_dir, out = make_ready_window("MergeTest")
        gui = window.gui_icon_tab
        gui.icons["full"] = Image.new("RGBA", (9, 9), (1, 1, 1, 255))
        gui.icons["half"] = Image.new("RGBA", (9, 9), (2, 2, 2, 255))

        item = window.item_tab
        fn = sorted(os.listdir(item.items_dir))[0]
        item.target_items.append({"filename": fn, "path": os.path.join(item.items_dir, fn)})
        item._get_or_create_config(fn)["effect"] = EC.BLINK

        root = tempfile.mkdtemp(prefix="ore_test_merge_")
        img = Image.new("RGBA", (9, 9), (9, 9, 9, 255))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        project = {
            "format_version": 2, "generated_by": "x",
            "target_blocks": [],
            "gui_icons": {"full": base64.b64encode(buf.getvalue()).decode("ascii")},
            "item_textures": {
                "target_items": [{"filename": fn}],
                "item_configs": {fn: {
                    "effect": "レインボーのみ", "frame_count": 16, "frametime": 2, "dark_factor": 0.35,
                }},
            },
        }
        with open(os.path.join(root, "oreHighlighterProject.json"), "w", encoding="utf-8") as f:
            json.dump(project, f, ensure_ascii=False)

        # 既存のブロック/GUI/アイテムがあるため通常はモード選択ダイアログが出る。
        # box.exec()を使う実装なのでQMessageBox.questionのモックだけでは止められないため、
        # ここではメソッド自体を直接差し替えて「マージ」を選んだことにする。
        bt._ask_project_import_mode = lambda: "merge"
        bt.import_project(root)

        self.assertEqual(list(gui.icons["full"].getdata())[0], (9, 9, 9, 255), "同名は上書きされるはず")
        self.assertEqual(list(gui.icons["half"].getdata())[0], (2, 2, 2, 255), "別名は残るはず（マージ）")
        self.assertEqual(item.item_configs[fn]["effect"], EC.RAINBOW)

    def test_replace_mode_wipes_gui_icons_not_in_project(self):
        window, bt, tmp, block_dir, out = make_ready_window("ReplaceTest")
        gui = window.gui_icon_tab
        gui.icons["full"] = Image.new("RGBA", (9, 9), (1, 1, 1, 255))
        gui.icons["half"] = Image.new("RGBA", (9, 9), (2, 2, 2, 255))

        root = tempfile.mkdtemp(prefix="ore_test_replace_")
        img = Image.new("RGBA", (9, 9), (7, 7, 7, 255))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        project = {
            "format_version": 2, "generated_by": "x",
            "target_blocks": [],
            "gui_icons": {"full": base64.b64encode(buf.getvalue()).decode("ascii")},
            "item_textures": {"target_items": [], "item_configs": {}},
        }
        with open(os.path.join(root, "oreHighlighterProject.json"), "w", encoding="utf-8") as f:
            json.dump(project, f, ensure_ascii=False)

        bt._ask_project_import_mode = lambda: "replace"
        bt.import_project(root)

        self.assertNotIn("half", gui.icons, "置き換えモードなのに古いアイコンが残っている")
        self.assertEqual(list(gui.icons["full"].getdata())[0], (7, 7, 7, 255))

    def test_missing_original_item_image_is_skipped_gracefully(self):
        """
        プロジェクトに記録されたアイテムの元テクスチャが、今読み込んでいる
        アイテムフォルダに存在しない場合、エラーにせず静かにスキップされること。
        """
        window, bt, tmp, block_dir, out = make_ready_window("SkipTest")
        root = tempfile.mkdtemp(prefix="ore_test_missing_")
        project = {
            "format_version": 2, "generated_by": "x",
            "target_blocks": [], "gui_icons": {},
            "item_textures": {
                "target_items": [{"filename": "存在しないアイテム.png"}],
                "item_configs": {"存在しないアイテム.png": {
                    "effect": "点滅", "frame_count": 2, "frametime": 2, "dark_factor": 0.35,
                }},
            },
        }
        with open(os.path.join(root, "oreHighlighterProject.json"), "w", encoding="utf-8") as f:
            json.dump(project, f, ensure_ascii=False)

        bt._ask_project_import_mode = lambda: "merge"
        bt.import_project(root)  # 例外が出なければ合格

        self.assertEqual(len(window.item_tab.target_items), 0)
        self.assertNotIn("存在しないアイテム.png", window.item_tab.item_configs)


if __name__ == "__main__":
    unittest.main()
