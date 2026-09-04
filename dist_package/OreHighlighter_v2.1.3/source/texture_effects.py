"""
Minecraft 鉱石視認性向上ツール - プロトタイプ
1枚のブロックテクスチャ（PNG）に対して、エフェクトをかけてアニメーションフレーム列を生成する基本ロジック。

対応エフェクト:
- blink_frames            : 点滅（明滅）
- outline_frames          : 枠線強調（縁を指定色で縁取り、点滅させる）
- outline_rainbow_frames  : 枠線だけが虹色に変化する（中身は加工しない）
- rainbow_frames          : レインボー（色相を回転させる）
- rainbow_gradient_frames : レインボー（斜めグラデーション。方向は reverse で切り替え）
- rainbow_and_outline_frames : レインボー＋枠線（両方とも同じ色相で変化）

出力:
- save_animated_texture() で、フレームを縦に連結したスプライトシート(.png)と
  対応する .mcmeta（アニメーション定義）を書き出す。

Copyright (c) 2026 旬茶
Licensed under the MIT License. 詳細は同梱の LICENSE ファイルを参照してください。
"""

from PIL import Image, ImageOps
import colorsys
import json
import os


def create_placeholder_ore_texture(size=16):
    """
    実テクスチャがまだ手元にない場合のテスト用に、
    それっぽい「鉱石ブロック」風のプレースホルダー画像を生成する。
    （本番では実際のMinecraftテクスチャPNGを読み込む想定）
    """
    img = Image.new("RGBA", (size, size), (90, 90, 95, 255))
    px = img.load()
    import random
    random.seed(42)
    for y in range(size):
        for x in range(size):
            # ベースの石っぽいノイズ
            noise = random.randint(-12, 12)
            base = 90 + noise
            px[x, y] = (base, base, base + 3, 255)
    # 鉱石の粒っぽい点を散らす（水色系＝ダイヤ風）
    for _ in range(14):
        cx, cy = random.randint(1, size - 2), random.randint(1, size - 2)
        color = (120 + random.randint(0, 60), 200 + random.randint(0, 55), 220, 255)
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                x, y = cx + dx, cy + dy
                if 0 <= x < size and 0 <= y < size and abs(dx) + abs(dy) <= 1:
                    px[x, y] = color
    return img


def blink_frames(image: Image.Image, frame_count: int = 2, dark_factor: float = 0.35):
    """
    明滅エフェクト。通常の明るさ ⇔ 暗く落とした状態を交互に繰り返すフレーム列を作る。
    frame_count=2 なら [通常, 暗い] の2コマ。
    """
    frames = [image.copy()]
    dark = Image.eval(image.convert("RGBA"), lambda v: v)  # ベースコピー
    r, g, b, a = image.convert("RGBA").split()
    r = r.point(lambda v: int(v * dark_factor))
    g = g.point(lambda v: int(v * dark_factor))
    b = b.point(lambda v: int(v * dark_factor))
    dark = Image.merge("RGBA", (r, g, b, a))
    frames.append(dark)
    # frame_countが3以上なら、通常/暗いを繰り返して埋める
    while len(frames) < frame_count:
        frames.append(frames[len(frames) % 2].copy())
    return frames[:frame_count]


def outline_frames(image: Image.Image, color=(255, 60, 60, 255), thickness: int = 1, frame_count: int = 2):
    """
    枠線強調エフェクト。画像の透明でないピクセルの外周に、指定色の縁取りを追加する。
    frame_count=2 で、縁取りあり⇔なし を交互に点滅させる（目立たせるため）。
    """
    base = image.convert("RGBA")
    w, h = base.size
    alpha = base.split()[-1]

    outlined = base.copy()
    px_alpha = alpha.load()
    px_out = outlined.load()

    for y in range(h):
        for x in range(w):
            if px_alpha[x, y] > 10:
                continue  # 元々不透明な部分は触らない（中身は保持）
            # 近傍に不透明ピクセルがあれば、この透明ピクセルを縁取り色にする
            is_edge = False
            for dx in range(-thickness, thickness + 1):
                for dy in range(-thickness, thickness + 1):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < w and 0 <= ny < h and px_alpha[nx, ny] > 10:
                        is_edge = True
                        break
                if is_edge:
                    break
            if is_edge:
                px_out[x, y] = color

    # 今回のプレースホルダーはブロック全面が不透明なので、外周1pxに枠を上書きする簡易版も用意
    bordered = base.copy()
    px_b = bordered.load()
    for x in range(w):
        for t in range(thickness):
            px_b[x, t] = color
            px_b[x, h - 1 - t] = color
    for y in range(h):
        for t in range(thickness):
            px_b[t, y] = color
            px_b[w - 1 - t, y] = color

    frames = [base.copy(), bordered]
    while len(frames) < frame_count:
        frames.append(frames[len(frames) % 2].copy())
    return frames[:frame_count]


def rainbow_frames(image: Image.Image, frame_count: int = 16):
    """
    レインボーエフェクト。画像の色相(Hue)を frame_count 段階でずらしたフレーム列を作る。
    彩度・明度は維持し、色相だけを回転させる。
    """
    base = image.convert("RGBA")
    w, h = base.size
    frames = []

    for i in range(frame_count):
        hue_shift = i / frame_count  # 0.0〜1.0
        new_img = Image.new("RGBA", (w, h))
        src = base.load()
        dst = new_img.load()
        for y in range(h):
            for x in range(w):
                r, g, b, a = src[x, y]
                if a == 0:
                    dst[x, y] = (0, 0, 0, 0)
                    continue
                hh, ss, vv = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
                hh = (hh + hue_shift) % 1.0
                nr, ng, nb = colorsys.hsv_to_rgb(hh, ss, vv)
                dst[x, y] = (int(nr * 255), int(ng * 255), int(nb * 255), a)
        frames.append(new_img)

    return frames


def rainbow_gradient_frames(image: Image.Image, frame_count: int = 16, band_count: float = 3,
                             reverse: bool = False, pattern_visibility: float = 0.4):
    """
    斜め方向に虹色の帯が並ぶグラデーションエフェクト。
    帯は frame_count 段階で斜め方向にスクロールするアニメーションになる
    （バニラのエンチャント光沢に近い、動く虹色の縞模様）。

    通常のrainbow_frames()と違い、色相は「その場のピクセル値」ではなく
    「画面内の位置（斜め距離）」で決まる。
    彩度・明度はできるだけ元の絵の陰影を保つよう、元のピクセルの値を流用する。

    band_count: 画像の対角線の中に何本分の虹色の帯を並べるか（多いほど帯が細かい）。
    reverse: False なら左上→右下方向、True なら右下→左上方向に帯が並ぶ
             （斜め距離の基準点を画像のどちらの角に置くかを反転させているだけで、
             　彩度・明度の扱いなど他のロジックは同じ）。
    pattern_visibility: 虹色を乗せる際、元のピクセル色をどれだけ残すか（0.0〜1.0）。
             0.0 なら虹色で完全に上書き（以前までの見た目）、1.0 なら虹色が乗らず
             元の絵そのまま。値を上げるほど、元のテクスチャの模様（陰影）が
             透けて見えやすくなる。既定値0.4は、模様を残しつつ虹色もはっきり
             見える程度のバランス。
    """
    base = image.convert("RGBA")
    w, h = base.size
    src = base.load()
    diag_len = max(w + h, 1)
    stripe_width = diag_len / max(band_count, 0.1)
    mix = max(0.0, min(1.0, pattern_visibility))
    frames = []

    for i in range(frame_count):
        offset = (i / frame_count) * stripe_width
        new_img = Image.new("RGBA", (w, h))
        dst = new_img.load()
        for y in range(h):
            for x in range(w):
                r, g, b, a = src[x, y]
                if a == 0:
                    dst[x, y] = (0, 0, 0, 0)
                    continue
                _, ss, vv = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
                # 元の彩度・明度が低すぎる（黒に近い/影の部分）と虹色が見えにくいので下駄を履かせる
                ss = max(ss, 0.55)
                vv = max(vv, 0.55)
                diag_pos = (w - 1 - x) + (h - 1 - y) if reverse else (x + y)
                hue = ((diag_pos + offset) / stripe_width) % 1.0
                nr, ng, nb = colorsys.hsv_to_rgb(hue, ss, vv)
                # 虹色で完全に置き換えるのではなく、pattern_visibilityの割合だけ
                # 元のピクセル色とブレンドする。これにより元のテクスチャの模様
                # （明暗のパターン）を残しつつ、虹色を半透明に重ねたような見た目になる。
                fr = int(r * mix + nr * 255 * (1 - mix))
                fg = int(g * mix + ng * 255 * (1 - mix))
                fb = int(b * mix + nb * 255 * (1 - mix))
                dst[x, y] = (fr, fg, fb, a)
        frames.append(new_img)

    return frames


def add_border(image: Image.Image, color=(255, 255, 255, 255), thickness: int = 1):
    """画像の外周thicknessピクセルを指定色で上書きする（枠線を追加する）。"""
    img = image.convert("RGBA").copy()
    w, h = img.size
    px = img.load()
    for x in range(w):
        for t in range(thickness):
            px[x, t] = color
            px[x, h - 1 - t] = color
    for y in range(h):
        for t in range(thickness):
            px[t, y] = color
            px[w - 1 - t, y] = color
    return img


def rainbow_and_outline_frames(image: Image.Image, frame_count: int = 16, thickness: int = 1,
                                border_saturation: float = 1.0, border_brightness: float = 1.0):
    """
    レインボー（色相回転）と枠線強調を組み合わせたフレーム列。
    中身の色も枠線の色も、同じ色相（そのフレームの虹色）に揃えて変化させる。
    border_saturation / border_brightness を下げると、枠線の主張を弱められる（0.0〜1.0）。
    """
    base_frames = rainbow_frames(image, frame_count=frame_count)
    result = []
    for i, frame in enumerate(base_frames):
        hue = i / frame_count
        r, g, b = colorsys.hsv_to_rgb(hue, border_saturation, border_brightness)
        border_color = (int(r * 255), int(g * 255), int(b * 255), 255)
        result.append(add_border(frame, color=border_color, thickness=thickness))
    return result


def outline_rainbow_frames(image: Image.Image, frame_count: int = 16, thickness: int = 1,
                            border_saturation: float = 0.7, border_brightness: float = 0.7):
    """
    枠線だけが虹色に変化し続けるフレーム列。中身の絵は一切加工しない
    （rainbow_and_outline_frames() と違い、ブロック本体の色は元のまま）。
    """
    base = image.convert("RGBA")
    frames = []
    for i in range(frame_count):
        hue = i / frame_count
        r, g, b = colorsys.hsv_to_rgb(hue, border_saturation, border_brightness)
        border_color = (int(r * 255), int(g * 255), int(b * 255), 255)
        frames.append(add_border(base, color=border_color, thickness=thickness))
    return frames


def save_animated_texture(frames, out_png_path: str, frametime: int = 2, interpolate: bool = False):
    """
    フレーム列を縦に連結したスプライトシートPNGと、対応する.mcmetaを書き出す。
    Minecraftのアニメーションテクスチャ形式：
      - PNGは 元の幅 x (元の高さ * フレーム数) の縦連結画像
      - .mcmeta で frametime（1コマの表示時間, 単位はtick=1/20秒）を指定
    """
    if not frames:
        raise ValueError("frames が空です")

    w, h = frames[0].size
    sheet = Image.new("RGBA", (w, h * len(frames)))
    for i, f in enumerate(frames):
        sheet.paste(f.convert("RGBA"), (0, i * h))

    os.makedirs(os.path.dirname(out_png_path) or ".", exist_ok=True)
    sheet.save(out_png_path)

    mcmeta = {
        "animation": {
            "frametime": frametime,
            "interpolate": interpolate
        }
    }
    with open(out_png_path + ".mcmeta", "w", encoding="utf-8") as f:
        json.dump(mcmeta, f, indent=2)

    return out_png_path, out_png_path + ".mcmeta"


def make_preview_strip(frames, out_path: str, scale: int = 8, gap: int = 2):
    """
    確認用：フレームを横一列に並べたプレビュー画像を作る（.mcmetaの縦連結とは別、目視確認専用）。
    """
    if not frames:
        raise ValueError("frames が空です")
    w, h = frames[0].size
    sw, sh = w * scale, h * scale
    total_w = sw * len(frames) + gap * (len(frames) - 1)
    strip = Image.new("RGBA", (total_w, sh), (30, 30, 30, 255))
    for i, f in enumerate(frames):
        big = f.convert("RGBA").resize((sw, sh), Image.NEAREST)
        strip.paste(big, (i * (sw + gap), 0), big)
    strip.save(out_path)
    return out_path