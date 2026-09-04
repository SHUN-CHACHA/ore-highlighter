"""
エフェクト定義の集約（effect_catalog.py）と後方互換のテスト。

背景:
  ブロックエフェクトタブとアイテムテクスチャ編集タブが、それぞれ独自の
  EFFECT_NAMES と _generate_frames_for() を持っていた。その結果、
  同じ効果なのに名前が違い（「レインボーのみ（斜めグラデーション）」と
  「レインボー（斜めグラデーション）」）、ブロック側にだけ追加された
  帯の本数・透過度がアイテムに反映されない機能差も生まれていた。

  そこで定義を effect_catalog.py に集約し、保存する値を「表示名」から
  「内部キー」に変更した。これにより表示名は自由にリネームできる。

このファイルでは以下を確認する:
  1. 内部キーと表示名が1対1で揃っていること
  2. 旧バージョンが保存した表示名（ブロック側・アイテム側の両表記）が
     すべて内部キーへ読み替えられること
  3. 旧形式のconfig/プロジェクトを読み込んでも設定が失われないこと
  4. アイテムでもブロックと同じエフェクトが使えること
"""

import json
import os
import tempfile
import unittest

from helpers import (  # noqa: F401
    make_window, make_texture_folder, silence_dialogs, silence_exec,
)
import effect_catalog as EC
from PIL import Image


class TestCatalogConsistency(unittest.TestCase):
    def test_every_key_has_a_display_name(self):
        for key in EC.ITEM_EFFECT_KEYS:
            self.assertIn(key, EC.DISPLAY_NAMES, f"{key} の表示名が無い")

    def test_display_names_are_unique(self):
        names = list(EC.DISPLAY_NAMES.values())
        self.assertEqual(len(names), len(set(names)), "表示名が重複している")

    def test_item_effects_include_all_block_effects(self):
        """アイテムでもブロックと同じエフェクトが全部使えること
        （以前はアイテム側に枠線系が無く、機能差になっていた）。"""
        for key in EC.BLOCK_EFFECT_KEYS:
            self.assertIn(key, EC.ITEM_EFFECT_KEYS)
        self.assertIn(EC.NONE, EC.ITEM_EFFECT_KEYS)
        self.assertNotIn(EC.NONE, EC.BLOCK_EFFECT_KEYS,
                         "ブロックは必ず何かのエフェクトを付ける前提なので「なし」は持たない")


class TestLegacyNameMigration(unittest.TestCase):
    """旧バージョンが保存していた表示名が、内部キーに読み替えられること。"""

    LEGACY_BLOCK = {
        "レインボー + 枠線": EC.RAINBOW_OUTLINE,
        "レインボーのみ": EC.RAINBOW,
        "レインボーのみ（斜めグラデーション）": EC.RAINBOW_GRADIENT,
        "枠線のみ": EC.OUTLINE,
        "枠線のみ（レインボー）": EC.OUTLINE_RAINBOW,
        "点滅": EC.BLINK,
    }
    LEGACY_ITEM = {
        "なし（静止画のみ）": EC.NONE,
        "レインボーのみ": EC.RAINBOW,
        "レインボー（斜めグラデーション）": EC.RAINBOW_GRADIENT,
        "点滅": EC.BLINK,
    }

    def test_legacy_block_names(self):
        for old, expected in self.LEGACY_BLOCK.items():
            self.assertEqual(EC.normalize_effect(old), expected, f"旧ブロック名 {old} を読めない")

    def test_legacy_item_names(self):
        for old, expected in self.LEGACY_ITEM.items():
            self.assertEqual(EC.normalize_effect(old), expected, f"旧アイテム名 {old} を読めない")

    def test_same_effect_from_both_tabs_maps_to_one_key(self):
        """表記が違っていた斜めグラデーションが、同じ内部キーに寄ること。"""
        self.assertEqual(
            EC.normalize_effect("レインボーのみ（斜めグラデーション）"),
            EC.normalize_effect("レインボー（斜めグラデーション）"),
        )

    def test_internal_keys_pass_through(self):
        for key in EC.ITEM_EFFECT_KEYS:
            self.assertEqual(EC.normalize_effect(key), key)

    def test_unknown_value_falls_back_to_default(self):
        self.assertEqual(EC.normalize_effect("知らないエフェクト", default=EC.BLINK), EC.BLINK)
        self.assertIsNone(EC.normalize_effect(None))


class TestLegacyProjectLoads(unittest.TestCase):
    """旧形式の oreHighlighterProject.json を開いても、エフェクト設定が失われないこと。"""

    def test_old_project_with_display_name_is_migrated(self):
        _tmp, block_dir, _item = make_texture_folder()
        filename = sorted(os.listdir(block_dir))[0]
        old_project = {
            "format_version": 3,
            "generated_by": "OreHighlighter v2.0.2",
            "target_blocks": [{
                "filename": filename,
                "effect": "枠線のみ（レインボー）",   # ← 旧表示名
                "frame_count": 16, "frametime": 2, "thickness": 2,
                "border_saturation": 0.7, "border_brightness": 0.7, "dark_factor": 0.35,
            }],
        }
        root = tempfile.mkdtemp(prefix="ore_test_legacy_effect_")
        with open(os.path.join(root, "oreHighlighterProject.json"), "w", encoding="utf-8") as f:
            json.dump(old_project, f, ensure_ascii=False)

        silence_dialogs()
        silence_exec()
        w = make_window()
        w.block_tab.load_textures_folder(block_dir)
        w.block_tab.import_project(root)

        self.assertEqual(len(w.block_tab.target_blocks), 1)
        loaded = w.block_tab.target_blocks[0]
        self.assertEqual(loaded["effect"], EC.OUTLINE_RAINBOW, "旧表示名が内部キーに移行していない")
        self.assertEqual(loaded["thickness"], 2, "他のパラメータまで既定値に戻ってしまっている")

        # 移行後の設定でフレーム生成まで通ること
        image = Image.open(loaded["path"]).convert("RGBA")
        frames = w.block_tab._generate_frames_for(image, loaded)
        self.assertGreater(len(frames), 1)

    def test_old_item_config_with_display_name_is_migrated(self):
        w = make_window()
        item = w.item_tab
        item.deserialize({
            "target_items": [{"filename": "diamond_pickaxe.png", "path": "/dev/null"}],
            "item_configs": {
                "diamond_pickaxe.png": {
                    "effect": "レインボー（斜めグラデーション）",  # ← アイテム側の旧表示名
                    "frame_count": 8, "frametime": 3, "dark_factor": 0.35,
                }
            },
        })
        cfg = item.item_configs["diamond_pickaxe.png"]
        self.assertEqual(cfg["effect"], EC.RAINBOW_GRADIENT)
        self.assertEqual(cfg["frame_count"], 8)
        # 旧アイテム設定に無かったキーは既定値で補われる
        self.assertEqual(cfg["gradient_band_count"], EC.DEFAULT_EFFECT_SETTINGS["gradient_band_count"])


class TestSharedFrameGeneration(unittest.TestCase):
    """ブロックとアイテムが同じ生成関数を使い、結果が一致すること。"""

    def test_block_and_item_produce_identical_frames(self):
        w = make_window()
        img = Image.new("RGBA", (16, 16), (100, 140, 200, 255))
        settings = dict(EC.DEFAULT_BLOCK_SETTINGS, effect=EC.RAINBOW_GRADIENT,
                        frame_count=4, gradient_band_count=5, gradient_transparency=0.2)
        block_frames = w.block_tab._generate_frames_for(img, settings)
        item_frames = w.item_tab._generate_frames_for(img, settings)
        self.assertEqual(len(block_frames), len(item_frames))
        for bf, itf in zip(block_frames, item_frames):
            self.assertEqual(bf.tobytes(), itf.tobytes())

    def test_item_gradient_now_honours_band_count(self):
        """以前はアイテム側が帯の本数・透過度を渡しておらず、設定しても効かなかった。"""
        w = make_window()
        img = Image.new("RGBA", (16, 16), (100, 140, 200, 255))
        few = w.item_tab._generate_frames_for(
            img, dict(EC.DEFAULT_ITEM_SETTINGS, effect=EC.RAINBOW_GRADIENT,
                      frame_count=2, gradient_band_count=1))
        many = w.item_tab._generate_frames_for(
            img, dict(EC.DEFAULT_ITEM_SETTINGS, effect=EC.RAINBOW_GRADIENT,
                      frame_count=2, gradient_band_count=8))
        self.assertNotEqual(few[0].tobytes(), many[0].tobytes(),
                            "帯の本数を変えても結果が変わっていない")

    def test_item_can_use_outline_effect(self):
        """アイテムでも枠線系エフェクトが使えること（以前は選択肢すら無かった）。"""
        w = make_window()
        img = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        img.putpixel((8, 8), (255, 255, 255, 255))
        frames = w.item_tab._generate_frames_for(
            img, dict(EC.DEFAULT_ITEM_SETTINGS, effect=EC.OUTLINE, border_color="#00ff00"))
        self.assertEqual(len(frames), 2)
        # outline_frames は [元の絵, 枠線あり] の2コマを交互に見せる
        self.assertEqual(frames[0].tobytes(), img.tobytes())
        self.assertNotEqual(frames[1].tobytes(), img.tobytes(), "枠線が描かれていない")


if __name__ == "__main__":
    unittest.main()
