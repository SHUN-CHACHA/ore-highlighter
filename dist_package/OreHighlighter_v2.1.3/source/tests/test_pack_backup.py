"""
バックアップ書き出しの共通化（pack_backup.py）に関するテスト。

背景:
  「既存プロジェクトを開く」（ブロックタブ）と「既存パックからGUIアイコンを読み込む」
  （GUIアイコンタブ）は、どちらも読み込み前に今の内容をバックアップできる。
  この流れが両タブでほぼ同一のコードとして二重実装されており、文言の主語だけが
  違う状態だった（片方だけ直して片方が古くなる事故のもと）。

  pack_backup.py に一本化したうえで、以下も改善している:
    - GUIアイコンのバックアップも、ブロック側と同じ安全なzip化
      （一時ファイルに書き切ってから os.replace で差し替え）を通るようになった
"""

import os
import unittest
import zipfile

from helpers import (  # noqa: F401
    make_window, make_ready_window, make_texture_folder, silence_dialogs,
)
import pack_backup
from PIL import Image


class TestBackupPackName(unittest.TestCase):
    def test_rename_mode_appends_date(self):
        name = pack_backup.backup_pack_name("MyPack", "rename")
        self.assertTrue(name.startswith("MyPack_"), name)
        self.assertNotEqual(name, "MyPack")

    def test_overwrite_mode_keeps_name(self):
        self.assertEqual(pack_backup.backup_pack_name("MyPack", "overwrite"), "MyPack")


class TestZipPackFolder(unittest.TestCase):
    def test_zip_contains_root_relative_paths_and_removes_folder(self):
        tmp, block_dir, _item = make_texture_folder()
        pack_root = os.path.join(tmp, "ZipMe")
        inner = os.path.join(pack_root, "assets", "minecraft")
        os.makedirs(inner)
        with open(os.path.join(pack_root, "pack.mcmeta"), "w", encoding="utf-8") as f:
            f.write("{}")
        Image.open(os.path.join(block_dir, sorted(os.listdir(block_dir))[0])).save(
            os.path.join(inner, "a.png"))

        zip_path = pack_backup.zip_pack_folder(pack_root)

        self.assertFalse(os.path.exists(pack_root), "zip化後にフォルダが残っている")
        with zipfile.ZipFile(zip_path) as z:
            names = z.namelist()
        self.assertIn("pack.mcmeta", names, "pack.mcmetaがzipのルート直下に無い")

    def test_existing_zip_survives_a_failed_run(self):
        """zipの書き込み中に失敗しても、前回の本番zipが壊れずに残ること
        （一時ファイルに書き切ってから os.replace で差し替える方式の確認）。"""
        tmp, _block_dir, _item = make_texture_folder()
        pack_root = os.path.join(tmp, "Keep")
        os.makedirs(pack_root)
        with open(os.path.join(pack_root, "pack.mcmeta"), "w", encoding="utf-8") as f:
            f.write("{}")

        zip_path = pack_root + ".zip"
        with open(zip_path, "wb") as f:
            f.write(b"previous-good-zip")

        original = pack_backup.zipfile.ZipFile

        def boom(*_args, **_kwargs):
            raise OSError("ディスクが一杯です（テスト用の擬似エラー）")

        pack_backup.zipfile.ZipFile = boom
        try:
            with self.assertRaises(OSError):
                pack_backup.zip_pack_folder(pack_root)
        finally:
            pack_backup.zipfile.ZipFile = original

        with open(zip_path, "rb") as f:
            self.assertEqual(f.read(), b"previous-good-zip", "前回のzipが壊された")
        self.assertFalse(os.path.exists(pack_root + ".zip.tmp"), "一時ファイルが残っている")
        self.assertTrue(os.path.isdir(pack_root), "失敗したのに元のフォルダが消えている")


class TestRunBackupExportFlow(unittest.TestCase):
    """run_backup_export() の分岐（中身なし／出力先なし／キャンセル／成功）。"""

    def setUp(self):
        self.window = make_window()

    def test_no_content_skips_and_continues(self):
        called = []
        ok = pack_backup.run_backup_export(
            self.window, has_content=False, pack_name="X", output_dir=None,
            write_pack=lambda root: called.append(root),
            confirm_text="", missing_output_message="", on_success=lambda *a: None,
        )
        self.assertTrue(ok, "書き出すものが無い場合は素通りで続行できるはず")
        self.assertEqual(called, [], "書き出すものが無いのに write_pack が呼ばれた")

    def test_missing_output_dir_aborts(self):
        silence_dialogs()
        ok = pack_backup.run_backup_export(
            self.window, has_content=True, pack_name="X", output_dir=None,
            write_pack=lambda root: None,
            confirm_text="", missing_output_message="出力先が無い",
            on_success=lambda *a: None,
        )
        self.assertFalse(ok)

    def test_cancel_aborts_without_writing(self):
        pack_backup.ask_backup_save_mode = staticmethod(lambda *a, **k: None)
        called = []
        ok = pack_backup.run_backup_export(
            self.window, has_content=True, pack_name="X", output_dir="/tmp",
            write_pack=lambda root: called.append(root),
            confirm_text="", missing_output_message="", on_success=lambda *a: None,
        )
        self.assertFalse(ok)
        self.assertEqual(called, [])


class TestBothTabsShareTheFlow(unittest.TestCase):
    """両タブのバックアップが、同じ共通フローを通って実際にzipを作れること。"""

    def test_block_tab_backup_writes_zip(self):
        silence_dialogs()
        pack_backup.ask_backup_save_mode = staticmethod(lambda *a, **k: "overwrite")
        window, bt, _tmp, _block_dir, out = make_ready_window("BackupBlock")

        self.assertTrue(bt._do_project_backup_export())

        zip_path = os.path.join(out, "BackupBlock.zip")
        self.assertTrue(os.path.exists(zip_path))
        self.assertTrue(bt.project_open_backup_btn.isVisible()
                        or bt.project_open_backup_btn.isVisibleTo(window))

    def test_gui_icon_tab_backup_writes_zip(self):
        silence_dialogs()
        pack_backup.ask_backup_save_mode = staticmethod(lambda *a, **k: "overwrite")
        window, bt, tmp, _block_dir, out = make_ready_window("BackupIcons")
        gt = window.gui_icon_tab
        # バリアントを1件だけ「保存済み」にする
        name = gt._variant_names()[0] if hasattr(gt, "_variant_names") else None
        if name is None:
            name = sorted(gt.icons.keys())[0] if gt.icons else "full"
        gt.icons[name] = Image.new("RGBA", (9, 9), (255, 0, 0, 255))

        self.assertTrue(gt._do_backup_export())

        zip_path = os.path.join(out, "BackupIcons.zip")
        self.assertTrue(os.path.exists(zip_path), f"{zip_path} が作られていない")
        with zipfile.ZipFile(zip_path) as z:
            self.assertIn("pack.mcmeta", z.namelist())
        del tmp, bt


if __name__ == "__main__":
    unittest.main()
