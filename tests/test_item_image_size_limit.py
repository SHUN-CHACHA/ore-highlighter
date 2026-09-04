"""
アイテムテクスチャの外部PNG画像の、受け付けサイズ上限のテスト。

これまでは64x64px以下に制限していたが、より高解像度の画像を使いたいという
要望により512x512px以下に緩和した。
（手持ち時の3D押し出し表現は高解像度だと崩れる場合がある、という制約自体は
　残っているが、それを承知の上でユーザーが選べるようにする）
"""

import os
import unittest

from helpers import make_ready_window, silence_dialogs  # noqa: F401
from PIL import Image
import item_texture_editor as ITE


class TestValidateItemImageSizeLimit(unittest.TestCase):
    """validate_item_image() 単体のテスト（UIを介さない）。"""

    def test_new_limit_is_512(self):
        self.assertEqual(ITE.REQUIRED_ITEM_IMAGE_SIZE, 512)

    def test_512x512_is_accepted(self):
        img = Image.new("RGBA", (512, 512), (10, 20, 30, 255))
        ok, result = ITE.validate_item_image(img)
        self.assertTrue(ok)
        self.assertEqual(result.size, (512, 512))

    def test_513x513_is_rejected(self):
        img = Image.new("RGBA", (513, 513), (10, 20, 30, 255))
        ok, message = ITE.validate_item_image(img)
        self.assertFalse(ok)
        self.assertIn("512", message)

    def test_64x64_still_accepted_backward_compat(self):
        """以前の上限だった64x64も、引き続き問題なく受け付けられること。"""
        img = Image.new("RGBA", (64, 64), (10, 20, 30, 255))
        ok, result = ITE.validate_item_image(img)
        self.assertTrue(ok)

    def test_non_square_still_rejected_regardless_of_size(self):
        img = Image.new("RGBA", (256, 128), (10, 20, 30, 255))
        ok, message = ITE.validate_item_image(img)
        self.assertFalse(ok)
        self.assertIn("正方形", message)


class TestImportImagePathAcceptsLargerImages(unittest.TestCase):
    """ItemTextureEditorTab.import_image_path() 経由（UI込み）のテスト。"""

    def setUp(self):
        silence_dialogs()
        self.window, self.bt, self.tmp, self.block_dir, self.out = make_ready_window("SizeTest")
        self.item = self.window.item_tab
        self.fn = sorted(os.listdir(self.item.items_dir))[0]
        self.item.target_items.append({
            "filename": self.fn, "path": os.path.join(self.item.items_dir, self.fn),
        })
        self.item._refresh_target_list()
        self.item._current_filename = self.fn
        self.item._effect_target_filenames = [self.fn]

    def test_importing_512px_image_succeeds(self):
        png_path = os.path.join(self.tmp, "big.png")
        Image.new("RGBA", (512, 512), (1, 2, 3, 255)).save(png_path)

        ok = self.item.import_image_path(png_path)

        self.assertTrue(ok)
        cfg = self.item.item_configs[self.fn]
        self.assertIsNotNone(cfg["custom_image"])
        self.assertEqual(cfg["custom_image"].size, (512, 512))

    def test_importing_too_large_image_still_rejected(self):
        png_path = os.path.join(self.tmp, "too_big.png")
        Image.new("RGBA", (600, 600), (1, 2, 3, 255)).save(png_path)

        ok = self.item.import_image_path(png_path)

        self.assertFalse(ok)
        self.assertIsNone(self.item.item_configs.get(self.fn, {}).get("custom_image"))


if __name__ == "__main__":
    unittest.main()
