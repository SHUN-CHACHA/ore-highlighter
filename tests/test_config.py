"""
config.json の保存・読み込みに関するテスト。

ここが壊れると「起動はするのに前回の設定が消える」という、
起動テストでは絶対に気づけない不具合になる。特にキー構成は
過去バージョンとの互換性があるため、安易に変えられない。
"""

import json
import os
import unittest

from helpers import (  # noqa: F401  (PyQt6より先にimportする必要がある)
    make_window, make_ready_window, silence_dialogs,
)
import effect_catalog as EC

# v1.2.3 以前から使われているトップレベルのキー。
# リファクタリングでタブへ処理を移しても、この位置は変えてはいけない。
EXPECTED_TOP_LEVEL_KEYS = [
    "textures_dir",
    "output_dir",
    "target_blocks",
    "pack_name",
    "pack_desc",
    "pack_icon_path",
    "gui_icons",
    "gui_icon_reference_dir",
    "item_textures",
]


class TestConfigRoundTrip(unittest.TestCase):
    def setUp(self):
        silence_dialogs()
        self.window, self.bt, self.tmp, self.block_dir, self.out = make_ready_window()

    def test_config_keys_are_backward_compatible(self):
        """ブロックタブ関連のキーがトップレベルに残っていること。"""
        cfg = self.window._current_config()
        for key in EXPECTED_TOP_LEVEL_KEYS:
            self.assertIn(key, cfg, f"config.json のキー「{key}」が失われている")

    def test_save_and_load_restores_state(self):
        """保存 → 別ウィンドウで読み込み → 状態が復元されること。"""
        self.bt.target_list.setCurrentRow(0)
        self.bt.effect_combo.setCurrentText("点滅")
        self.bt.dark_factor_spin.setValue(0.5)

        cfg_path = os.path.join(self.tmp, "saved.json")
        self.window._save_config_to_path(cfg_path)

        other = make_window()
        other._load_config_from_path(cfg_path)

        self.assertEqual(len(other.block_tab.target_blocks), 3)
        self.assertEqual(other.block_tab.target_blocks[0]["effect"], EC.BLINK)
        self.assertEqual(other.block_tab.target_blocks[0]["dark_factor"], 0.5)
        self.assertEqual(other.block_tab.pack_name_edit.text(), "TestPack")
        self.assertEqual(other.block_tab.output_dir, self.out)

    def test_apply_config_sets_item_dir(self):
        """
        読み込み順序の検証。ブロックタブが textures_dir を確定させる過程で
        アイテムタブの items_dir も設定される。この順序が崩れると、
        アイテムタブが「元テクスチャの場所を知らない」状態になる。
        """
        cfg_path = os.path.join(self.tmp, "saved.json")
        self.window._save_config_to_path(cfg_path)

        other = make_window()
        other._load_config_from_path(cfg_path)

        expected_item_dir = os.path.join(os.path.dirname(self.block_dir), "item")
        self.assertEqual(other.item_tab.items_dir, expected_item_dir)

    def test_config_is_valid_json_utf8(self):
        """日本語（ブロック名・エフェクト名）が化けずに保存されること。"""
        cfg_path = os.path.join(self.tmp, "saved.json")
        self.window._save_config_to_path(cfg_path)
        with open(cfg_path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["target_blocks"][0]["effect"], EC.RAINBOW_OUTLINE)

    def test_missing_texture_files_are_dropped_on_load(self):
        """
        保存時に存在したテクスチャが、読み込み時に無くなっていた場合は
        黙って除外されること（別PC・別バージョンのjarで開いたケース）。
        """
        cfg_path = os.path.join(self.tmp, "saved.json")
        self.window._save_config_to_path(cfg_path)

        with open(cfg_path, encoding="utf-8") as f:
            data = json.load(f)
        data["target_blocks"][0]["path"] = os.path.join(self.tmp, "存在しない.png")
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

        other = make_window()
        other._load_config_from_path(cfg_path)
        self.assertEqual(len(other.block_tab.target_blocks), 2)


if __name__ == "__main__":
    unittest.main()
