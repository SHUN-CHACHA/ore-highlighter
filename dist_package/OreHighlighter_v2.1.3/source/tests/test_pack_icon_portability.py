"""
パックアイコン（pack.png の元画像）のPC間持ち出しのテスト。

背景:
  カスタムのパックアイコンを選んでも、これまでは self.pack_icon_path に
  ローカルの絶対パスを持つだけで、oreHighlighterProject.json には一切
  含まれていなかった。そのため、別PCでこのプロジェクトを開いて再生成すると、
  選んだカスタムアイコンのファイルはそのPCに存在せず、意図せずアプリ既定の
  アイコンに戻ってしまう不具合があった。

  対策として、カスタムアイコンを選んでいる場合のみ画像データをbase64で
  oreHighlighterProject.json に埋め込み（アプリ既定のアイコンはどのPCにも
  同梱されているので埋め込み不要）、プロジェクトを開いたときに復元するようにした。
"""

import json
import os
import unittest
import zipfile

from helpers import make_ready_window, make_window, silence_dialogs  # noqa: F401
from PIL import Image


class TestPackIconPortability(unittest.TestCase):
    def setUp(self):
        silence_dialogs()
        self.window, self.bt, self.tmp, self.block_dir, self.out = make_ready_window("IconTest")
        self.custom_icon_path = os.path.join(self.tmp, "custom_icon.png")
        Image.new("RGBA", (40, 20), (10, 200, 30, 255)).save(self.custom_icon_path)  # 非正方形も試す

    def test_custom_icon_embedded_in_generated_project(self):
        self.bt.pack_icon_path = self.custom_icon_path
        self.window.on_generate()

        zip_path = os.path.join(self.out, "IconTest.zip")
        with zipfile.ZipFile(zip_path) as z:
            project = json.loads(z.read("oreHighlighterProject.json").decode("utf-8"))

        self.assertIn("pack_icon_b64", project)
        self.assertIsNotNone(project["pack_icon_b64"])

        import base64
        import io
        decoded = Image.open(io.BytesIO(base64.b64decode(project["pack_icon_b64"]))).convert("RGBA")
        original = Image.open(self.custom_icon_path).convert("RGBA")
        self.assertEqual(decoded.tobytes(), original.tobytes())

    def test_default_icon_not_embedded(self):
        self.bt.pack_icon_path = None
        self.window.on_generate()

        zip_path = os.path.join(self.out, "IconTest.zip")
        with zipfile.ZipFile(zip_path) as z:
            project = json.loads(z.read("oreHighlighterProject.json").decode("utf-8"))

        self.assertIn("pack_icon_b64", project)
        self.assertIsNone(project["pack_icon_b64"])

    def test_opening_project_on_another_pc_restores_custom_icon(self):
        """PC-Aでカスタムアイコンを設定・生成 → PC-Bでそのzipをプロジェクトとして開く。"""
        self.bt.pack_icon_path = self.custom_icon_path
        self.window.on_generate()
        zip_path = os.path.join(self.out, "IconTest.zip")

        pc_b = make_window()
        pc_b.block_tab.load_textures_folder(self.block_dir)
        extract_dir = os.path.join(self.tmp, "pc_b_extract")
        os.makedirs(extract_dir)
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(extract_dir)

        pc_b.block_tab._start_project_import(extract_dir, origin_kind="zip", origin_path=zip_path)

        self.assertIsNotNone(pc_b.block_tab.pack_icon_path)
        self.assertTrue(os.path.exists(pc_b.block_tab.pack_icon_path))
        restored = Image.open(pc_b.block_tab.pack_icon_path).convert("RGBA")
        original = Image.open(self.custom_icon_path).convert("RGBA")
        self.assertEqual(restored.tobytes(), original.tobytes())

        # PC-Bで改めて生成したときも、同じカスタムアイコンがpack.pngに使われること
        pc_b.block_tab.output_dir = os.path.join(self.tmp, "pc_b_out")
        os.makedirs(pc_b.block_tab.output_dir)
        pc_b.block_tab.pack_name_edit.setText("FromPCB")
        pc_b.on_generate()
        with zipfile.ZipFile(os.path.join(pc_b.block_tab.output_dir, "FromPCB.zip")) as z:
            packpng = Image.open(__import__("io").BytesIO(z.read("pack.png"))).convert("RGBA")
        # pack.pngは128x128にリサイズされるので、色だけ比較する（左上ピクセル）
        self.assertEqual(packpng.getpixel((0, 0))[:3], (10, 200, 30))

    def test_opening_project_with_default_icon_resets_current_custom_icon(self):
        """
        PC-A（今のセッション）が既に別のカスタムアイコンを設定している状態で、
        「アプリ既定のアイコンを使っていたプロジェクト」を開いたら、
        そちらに揃えて既定アイコンへ戻ること。
        """
        self.bt.pack_icon_path = None
        self.window.on_generate()  # 既定アイコンで生成
        zip_path = os.path.join(self.out, "IconTest.zip")

        pc_b = make_window()
        pc_b.block_tab.load_textures_folder(self.block_dir)
        pc_b.block_tab.pack_icon_path = self.custom_icon_path  # 元々は別のカスタムアイコンを使っていた

        extract_dir = os.path.join(self.tmp, "pc_b_extract2")
        os.makedirs(extract_dir)
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(extract_dir)
        pc_b.block_tab._start_project_import(extract_dir, origin_kind="zip", origin_path=zip_path)

        self.assertIsNone(pc_b.block_tab.pack_icon_path)

    def test_old_format_project_without_pack_icon_key_leaves_current_icon_untouched(self):
        """
        format_version 2以前（pack_icon_b64キーが無い）のプロジェクトを開いても、
        今設定中のパックアイコンが勝手に変わらないこと（絶対パス埋め込みではなく
        キー自体が存在しないので「既定に戻す」と区別できる必要がある）。
        """
        first_filename = sorted(os.listdir(self.block_dir))[0]
        old_project = {
            "format_version": 2,
            "generated_by": "OreHighlighter v2.0.1",
            "target_blocks": [{
                "filename": first_filename, "effect": "枠線のみ",
                "frame_count": 16, "frametime": 2, "thickness": 1,
                "border_saturation": 0.7, "border_brightness": 0.7, "dark_factor": 0.35,
                "border_color": "#ff3c3c", "gradient_band_count": 3, "gradient_transparency": 0.4,
            }],
            "gui_icons": {},
            "item_textures": {"target_items": [], "item_configs": {}},
            # pack_icon_b64キー自体が無い（古い形式を再現）
        }
        old_root = os.path.join(self.tmp, "old_format_project")
        os.makedirs(old_root)
        with open(os.path.join(old_root, "oreHighlighterProject.json"), "w", encoding="utf-8") as f:
            json.dump(old_project, f, ensure_ascii=False)

        other = make_window()
        other.block_tab.load_textures_folder(self.block_dir)
        other.block_tab.pack_icon_path = self.custom_icon_path

        other.block_tab._start_project_import(old_root)

        self.assertEqual(other.block_tab.pack_icon_path, self.custom_icon_path)


if __name__ == "__main__":
    unittest.main()
