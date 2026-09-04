"""
ブロックエフェクト（枠線色の指定・枠線のみレインボー・斜めグラデーション）のテスト。

【エフェクト名の扱いについて】
以前は表示名そのもの（"枠線のみ" 等）が config.json や配布パックの
oreHighlighterProject.json に保存されていたため、表示名をリネームできなかった。
現在は effect_catalog.py の内部キー（"outline" 等）を保存する方式に変えたので、
表示名は自由に変えられる。旧バージョンが保存した表示名は
effect_catalog.LEGACY_NAME_TO_KEY で内部キーに読み替える。

このファイルでは「新しい内部キーで保存されること」と「旧表示名でも読めること」の
両方を確認する。
"""

import json
import os
import tempfile
import unittest

from helpers import (  # noqa: F401
    make_window, make_ready_window, silence_dialogs,
)
import effect_catalog as EC
import block_tab as BT
from texture_effects import rainbow_gradient_frames, outline_frames, outline_rainbow_frames
from PIL import Image


class TestTextureEffectsFunctions(unittest.TestCase):
    """texture_effects.py 側の純粋関数のテスト（UIを介さない）。"""

    def test_rainbow_gradient_reverse_false_matches_original_behavior(self):
        """
        reverse=False が既定値であること（reverseを省略した呼び出しと、
        明示的にreverse=Falseを渡した呼び出しが1ピクセルも変わらないこと）。
        ※ pattern_visibility（透過度）の既定値は変更履歴があるが、この比較は
        　 両辺とも同じ既定値を使うため、その変更の影響は受けない。
        """
        img = Image.new("RGBA", (8, 8), (200, 200, 200, 255))
        with_default = rainbow_gradient_frames(img, frame_count=4, band_count=2)
        explicit_false = rainbow_gradient_frames(img, frame_count=4, band_count=2, reverse=False)
        for a, b in zip(with_default, explicit_false):
            self.assertEqual(list(a.getdata()), list(b.getdata()))

    def test_rainbow_gradient_reverse_flips_diagonal_direction(self):
        """reverse=True で、左上と右下の色が入れ替わること（右下→左上方向になる）。"""
        img = Image.new("RGBA", (8, 8), (200, 200, 200, 255))
        normal = rainbow_gradient_frames(img, frame_count=1, band_count=1, reverse=False)[0]
        reversed_ = rainbow_gradient_frames(img, frame_count=1, band_count=1, reverse=True)[0]
        self.assertEqual(reversed_.getpixel((0, 0)), normal.getpixel((7, 7)))
        self.assertEqual(reversed_.getpixel((7, 7)), normal.getpixel((0, 0)))

    def test_outline_frames_accepts_custom_color(self):
        img = Image.new("RGBA", (8, 8), (10, 10, 10, 255))
        frames = outline_frames(img, color=(0, 255, 0, 255), thickness=1, frame_count=2)
        self.assertEqual(frames[1].getpixel((0, 0)), (0, 255, 0, 255))
        self.assertEqual(frames[0].getpixel((0, 0)), (10, 10, 10, 255))

    def test_outline_rainbow_frames_animates_border_only(self):
        """中身のピクセルは一切変化せず、枠線だけがフレームごとに色を変えること。"""
        img = Image.new("RGBA", (8, 8), (10, 10, 10, 255))
        frames = outline_rainbow_frames(
            img, frame_count=4, thickness=1, border_saturation=1.0, border_brightness=1.0
        )
        self.assertEqual(len(frames), 4)
        for f in frames:
            self.assertEqual(f.getpixel((4, 4)), (10, 10, 10, 255), "中身が変化している")
        corner_colors = {f.getpixel((0, 0)) for f in frames}
        self.assertEqual(len(corner_colors), 4, "枠線の色がフレームごとに変化していない")

    def test_gradient_pattern_visibility_1_leaves_original_untouched(self):
        """pattern_visibility=1.0 なら、虹色は一切乗らず元の絵そのままになること。"""
        img = Image.new("RGBA", (8, 8), (37, 91, 142, 255))
        frames = rainbow_gradient_frames(img, frame_count=3, band_count=2, pattern_visibility=1.0)
        for f in frames:
            self.assertEqual(list(f.getdata()), list(img.getdata()))

    def test_gradient_pattern_visibility_0_matches_fully_opaque_rainbow(self):
        """pattern_visibility=0.0 は、以前までの「虹色で完全に上書き」の見た目と一致すること。"""
        img = Image.new("RGBA", (8, 8), (37, 91, 142, 255))
        opaque = rainbow_gradient_frames(img, frame_count=3, band_count=2, pattern_visibility=0.0)
        # 手計算の「完全上書き」相当（従来ロジック）と比較する
        import colorsys
        w, h = img.size
        diag_len = w + h
        stripe_width = diag_len / 2
        expected_first_pixel = None
        _, ss, vv = colorsys.rgb_to_hsv(37 / 255, 91 / 255, 142 / 255)
        ss, vv = max(ss, 0.55), max(vv, 0.55)
        hue = (0 / stripe_width) % 1.0  # x=0,y=0 の1フレーム目
        nr, ng, nb = colorsys.hsv_to_rgb(hue, ss, vv)
        expected_first_pixel = (int(nr * 255), int(ng * 255), int(nb * 255), 255)
        self.assertEqual(opaque[0].getpixel((0, 0)), expected_first_pixel)

    def test_gradient_pattern_visibility_partial_blends_between_original_and_rainbow(self):
        """0と1の中間なら、元の色と虹色の中間的な値になること（模様が透けて見える状態）。"""
        img = Image.new("RGBA", (8, 8), (37, 91, 142, 255))
        opaque = rainbow_gradient_frames(img, frame_count=1, band_count=2, pattern_visibility=0.0)[0]
        half = rainbow_gradient_frames(img, frame_count=1, band_count=2, pattern_visibility=0.5)[0]
        untouched = rainbow_gradient_frames(img, frame_count=1, band_count=2, pattern_visibility=1.0)[0]

        op = opaque.getpixel((3, 5))
        hp = half.getpixel((3, 5))
        up = untouched.getpixel((3, 5))
        self.assertEqual(up, (37, 91, 142, 255))
        # 中間値は、完全上書きと元の絵のちょうど間くらいになっているはず
        for c_op, c_hp, c_up in zip(op[:3], hp[:3], up[:3]):
            self.assertTrue(
                min(c_op, c_up) - 2 <= c_hp <= max(c_op, c_up) + 2,
                f"中間値になっていない: opaque={op} half={hp} untouched={up}",
            )


class TestBlockTabNewEffects(unittest.TestCase):
    def setUp(self):
        silence_dialogs()
        self.window, self.bt, self.tmp, self.block_dir, self.out = make_ready_window("EffectTest")

    def test_all_block_effects_are_selectable(self):
        """ブロック用の6エフェクトが、内部キー付きでコンボボックスに並んでいること。"""
        keys = [self.bt.effect_combo.itemData(i)
                for i in range(self.bt.effect_combo.count())]
        self.assertEqual(keys, EC.BLOCK_EFFECT_KEYS)
        for key in keys:
            self.assertIn(key, EC.DISPLAY_NAMES)

    def test_effect_is_saved_as_internal_key_not_display_name(self):
        """保存されるのは表示名ではなく内部キーであること
        （これが崩れると、表示名を変えた瞬間に過去の設定が読めなくなる）。"""
        self.bt.target_list.setCurrentRow(0)
        self.bt.effect_combo.setCurrentText("枠線")
        self.assertEqual(self.bt.target_blocks[0]["effect"], EC.OUTLINE)

    def test_border_color_picker_updates_target_block(self):
        self.bt.target_list.setCurrentRow(0)
        self.bt.effect_combo.setCurrentText("枠線")
        self.assertTrue(self.bt.border_color_btn.isEnabled())
        self.assertFalse(self.bt.border_saturation_spin.isEnabled())

        self.bt._current_border_color = "#00ff00"
        self.bt._update_border_color_button()
        self.bt.on_editor_changed()

        self.assertEqual(self.bt.target_blocks[0]["border_color"], "#00ff00")
        self.assertEqual(self.bt.border_color_btn.text(), "#00ff00")

    def test_outline_rainbow_param_visibility(self):
        self.bt.target_list.setCurrentRow(0)
        self.bt.effect_combo.setCurrentText("枠線（レインボー）")
        self.assertTrue(self.bt.frame_count_spin.isEnabled())
        self.assertTrue(self.bt.thickness_spin.isEnabled())
        self.assertTrue(self.bt.border_saturation_spin.isEnabled())
        self.assertTrue(self.bt.border_brightness_spin.isEnabled())
        self.assertFalse(
            self.bt.border_color_btn.isEnabled(),
            "レインボー枠線では色は自動計算なので、固定色ボタンは無効のはず",
        )

    def test_gradient_param_visibility_and_band_count(self):
        self.bt.target_list.setCurrentRow(0)
        self.bt.effect_combo.setCurrentText("レインボー（斜めグラデ）")
        self.assertTrue(self.bt.frame_count_spin.isEnabled())
        self.assertTrue(self.bt.gradient_band_count_spin.isEnabled())
        self.assertTrue(self.bt.gradient_transparency_spin.isEnabled())
        self.assertFalse(self.bt.thickness_spin.isEnabled())

        self.bt.gradient_band_count_spin.setValue(5)
        self.assertEqual(self.bt.target_blocks[0]["gradient_band_count"], 5)

    def test_gradient_transparency_default_and_editing(self):
        self.bt.target_list.setCurrentRow(0)
        self.bt.effect_combo.setCurrentText("レインボー（斜めグラデ）")

        # 既定値は「模様が透けて見える」よう0より大きい
        self.assertEqual(
            self.bt.gradient_transparency_spin.value(),
            BT.DEFAULT_BLOCK_SETTINGS["gradient_transparency"],
        )
        self.assertEqual(
            self.bt.target_blocks[0]["gradient_transparency"],
            BT.DEFAULT_BLOCK_SETTINGS["gradient_transparency"],
        )

        self.bt.gradient_transparency_spin.setValue(0.8)
        self.assertEqual(self.bt.target_blocks[0]["gradient_transparency"], 0.8)

        # 他のエフェクトを選ぶと無効化される（枠線の太さなどと同じ扱い）
        self.bt.effect_combo.setCurrentText("点滅")
        self.assertFalse(self.bt.gradient_transparency_spin.isEnabled())

    def test_preview_works_for_all_new_effects(self):
        for effect in ("レインボー（斜めグラデ）", "枠線（レインボー）", "枠線"):
            self.bt.target_list.setCurrentRow(0)
            self.bt.effect_combo.setCurrentText(effect)
            self.bt.on_preview()
            self.assertTrue(os.path.exists(self.bt._preview_gif_path))
            self.assertGreater(os.path.getsize(self.bt._preview_gif_path), 0)

    def test_generated_pack_includes_new_effect_settings(self):
        self.bt.target_list.setCurrentRow(0)
        self.bt.effect_combo.setCurrentText("枠線")
        self.bt._current_border_color = "#00ff00"
        self.bt._update_border_color_button()
        self.bt.on_editor_changed()

        self.bt.target_list.setCurrentRow(1)
        self.bt.effect_combo.setCurrentText("枠線（レインボー）")

        self.bt.target_list.setCurrentRow(2)
        self.bt.effect_combo.setCurrentText("レインボー（斜めグラデ）")

        self.window.on_generate()

        import zipfile
        zip_path = os.path.join(self.out, "EffectTest.zip")
        with zipfile.ZipFile(zip_path) as z:
            self.assertIsNone(z.testzip())
            project = json.loads(z.read("oreHighlighterProject.json").decode("utf-8"))

        effects = [b["effect"] for b in project["target_blocks"]]
        self.assertIn(EC.OUTLINE, effects)
        self.assertIn(EC.OUTLINE_RAINBOW, effects)
        self.assertIn(EC.RAINBOW_GRADIENT, effects)
        self.assertEqual(project["target_blocks"][0]["border_color"], "#00ff00")

    def test_old_project_without_new_keys_loads_with_defaults(self):
        """
        v1.2.4以前に作られた（border_color / gradient_band_count を持たない）
        oreHighlighterProject.json を読み込んでもエラーにならず、既定値で補われること。
        """
        first_filename = sorted(os.listdir(self.block_dir))[0]
        old_project = {
            "format_version": 1,
            "generated_by": "OreHighlighter v1.2.3",
            "target_blocks": [{
                "filename": first_filename,
                "effect": "枠線のみ",
                "frame_count": 16, "frametime": 2, "thickness": 1,
                "border_saturation": 0.7, "border_brightness": 0.7, "dark_factor": 0.35,
            }],
        }
        old_root = tempfile.mkdtemp(prefix="ore_test_oldproj_")
        with open(os.path.join(old_root, "oreHighlighterProject.json"), "w", encoding="utf-8") as f:
            json.dump(old_project, f, ensure_ascii=False)

        other = make_window()
        other.block_tab.load_textures_folder(self.block_dir)
        other.block_tab.import_project(old_root)

        self.assertEqual(len(other.block_tab.target_blocks), 1)
        loaded = other.block_tab.target_blocks[0]
        self.assertEqual(loaded["border_color"], BT.DEFAULT_BLOCK_SETTINGS["border_color"])
        self.assertEqual(loaded["gradient_band_count"], BT.DEFAULT_BLOCK_SETTINGS["gradient_band_count"])
        self.assertEqual(loaded["gradient_transparency"], BT.DEFAULT_BLOCK_SETTINGS["gradient_transparency"])

        # フレーム生成までエラーなく通ること（KeyErrorが出ないことの実地確認）
        image = Image.open(loaded["path"]).convert("RGBA")
        frames = other.block_tab._generate_frames_for(image, loaded)
        self.assertEqual(len(frames), 2)

    def test_old_config_without_new_keys_falls_back_to_defaults(self):
        """config.json 側でも同様に、新キーが無くても既定値で補われること。"""
        self.bt.target_list.setCurrentRow(1)
        self.bt.effect_combo.setCurrentText("レインボー（斜めグラデ）")
        self.bt.gradient_band_count_spin.setValue(7)

        cfg_path = os.path.join(self.tmp, "cfg.json")
        self.window._save_config_to_path(cfg_path)

        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
        for b in cfg["target_blocks"]:
            b.pop("border_color", None)
            b.pop("gradient_band_count", None)
            b.pop("gradient_transparency", None)
        old_cfg_path = os.path.join(self.tmp, "old_cfg.json")
        with open(old_cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False)

        other = make_window()
        other._load_config_from_path(old_cfg_path)
        self.assertEqual(
            other.block_tab.target_blocks[0]["border_color"],
            BT.DEFAULT_BLOCK_SETTINGS["border_color"],
        )
        self.assertEqual(
            other.block_tab.target_blocks[1]["gradient_band_count"],
            BT.DEFAULT_BLOCK_SETTINGS["gradient_band_count"],
        )
        self.assertEqual(
            other.block_tab.target_blocks[1]["gradient_transparency"],
            BT.DEFAULT_BLOCK_SETTINGS["gradient_transparency"],
        )


if __name__ == "__main__":
    unittest.main()
