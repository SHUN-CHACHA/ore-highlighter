"""
自動保存する設定（config.json）の保存先に関するテスト。

背景:
  配布はGitHubのzipで、バージョンアップのたびに「新しいzipを展開して
  古いフォルダごと入れ替える／上書きする」という運用になりやすい。
  以前は自動保存先がexe本体と同じフォルダ（AUTO_CONFIG_PATH = APP_DIR/config.json）
  だったため、そうした運用だと毎回設定が失われていた。

  対策として、自動保存先をOS標準のユーザーデータ置き場（Windowsなら
  %APPDATA%\\OreHighlighter\\config.json）に変更し、exe本体のフォルダとは
  切り離した。あわせて、旧バージョンの保存先にだけ設定が残っている場合は、
  初回起動時に一度だけ新しい場所へ自動でコピーする（LEGACY_AUTO_CONFIG_PATH）。
"""

import json
import os
import tempfile
import unittest

from helpers import make_window, get_app  # noqa: F401
import main as M


def _sample_config(pack_name="MigratedPack"):
    return {
        "pack_name": pack_name,
        "pack_desc": "",
        "output_dir": "",
        "textures_dir": "",
        "target_blocks": [],
        "gui_icons": {},
        "gui_icon_reference_dir": None,
        "item_textures": {},
    }


class TestAutoConfigPathIsOutsideAppDir(unittest.TestCase):
    def test_auto_config_path_is_not_next_to_app_dir_by_default(self):
        """
        importしただけの状態（テストによる上書き前）でも、既定のAUTO_CONFIG_PATHは
        APP_DIR（exe本体と同じフォルダ）の直下ではないこと。
        """
        self.assertNotEqual(
            os.path.dirname(M.__dict__.get("LEGACY_AUTO_CONFIG_PATH", "")),
            "",
        )
        # モジュール定義そのもの（ソースコード上の構造）を見て、
        # AUTO_CONFIG_PATH が USER_DATA_DIR 由来であることを確認する。
        import inspect
        src = inspect.getsource(M)
        self.assertIn('AUTO_CONFIG_PATH = os.path.join(USER_DATA_DIR, "config.json")', src)
        self.assertIn('LEGACY_AUTO_CONFIG_PATH = os.path.join(APP_DIR, "config.json")', src)


class TestLegacyMigration(unittest.TestCase):
    def setUp(self):
        get_app()
        self.new_dir = tempfile.mkdtemp(prefix="ore_test_new_cfg_")
        self.legacy_dir = tempfile.mkdtemp(prefix="ore_test_legacy_cfg_")
        M.AUTO_CONFIG_PATH = os.path.join(self.new_dir, "config.json")
        M.LEGACY_AUTO_CONFIG_PATH = os.path.join(self.legacy_dir, "config.json")

    def _write_legacy_config(self, pack_name="MigratedPack"):
        with open(M.LEGACY_AUTO_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(_sample_config(pack_name), f)

    def test_legacy_config_is_copied_to_the_new_location_on_startup(self):
        self._write_legacy_config()
        self.assertFalse(os.path.exists(M.AUTO_CONFIG_PATH))

        win = M.OreHighlighterWindow()

        self.assertTrue(os.path.exists(M.AUTO_CONFIG_PATH),
                        "旧い保存先の設定が、新しい保存先へコピーされていない")
        win.close()

    def test_migrated_settings_are_actually_loaded(self):
        self._write_legacy_config(pack_name="MigratedPack")
        win = M.OreHighlighterWindow()
        self.assertEqual(win.block_tab.pack_name_edit.text(), "MigratedPack")
        win.close()

    def test_no_crash_when_neither_location_has_a_config(self):
        # LEGACY_AUTO_CONFIG_PATHもAUTO_CONFIG_PATHも存在しない、まっさらな状態。
        win = M.OreHighlighterWindow()  # 例外が出なければOK
        self.assertFalse(os.path.exists(M.AUTO_CONFIG_PATH))
        win.close()

    def test_existing_new_location_is_not_overwritten_by_a_stale_legacy_file(self):
        """
        新しい保存先に既に（新しいバージョンで保存した）設定がある場合、
        旧い保存先の古い内容で上書きしてしまわないこと。
        """
        os.makedirs(os.path.dirname(M.AUTO_CONFIG_PATH), exist_ok=True)
        with open(M.AUTO_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(_sample_config(pack_name="AlreadyOnNewLocation"), f)
        self._write_legacy_config(pack_name="OldStaleName")

        win = M.OreHighlighterWindow()
        self.assertEqual(win.block_tab.pack_name_edit.text(), "AlreadyOnNewLocation")
        win.close()


class TestAutoSaveCreatesTheFolder(unittest.TestCase):
    def test_closing_the_window_creates_the_user_data_dir_if_missing(self):
        get_app()
        base = tempfile.mkdtemp(prefix="ore_test_autosave_")
        # わざとまだ存在しないサブフォルダにする（初回起動相当）。
        M.AUTO_CONFIG_PATH = os.path.join(base, "not_yet_created", "config.json")
        M.LEGACY_AUTO_CONFIG_PATH = os.path.join(
            tempfile.mkdtemp(prefix="ore_test_autosave_legacy_"), "config.json"
        )
        win = make_window()
        win.close()
        self.assertTrue(os.path.exists(M.AUTO_CONFIG_PATH),
                        "終了時の自動保存で、まだ無いフォルダが作られていない")


if __name__ == "__main__":
    unittest.main()
