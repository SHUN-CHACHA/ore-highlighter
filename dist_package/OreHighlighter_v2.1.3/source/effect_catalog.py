"""
エフェクトの定義を1箇所にまとめたモジュール（UI非依存）。

【なぜこのモジュールがあるか】
以前は、ブロックエフェクトタブとアイテムテクスチャ編集タブがそれぞれ独自に
EFFECT_NAMES と _generate_frames_for() を持っていた。その結果:

  - 同じ効果なのに名前が違った
    （ブロック「レインボーのみ（斜めグラデーション）」／アイテム「レインボー（斜めグラデーション）」）
  - ブロック側に後から追加した斜めグラデーションの「帯の本数」「透過度」が
    アイテム側に反映されておらず、機能差が生まれていた
  - アイテム側では枠線系のエフェクトがまるごと使えなかった

これらを避けるため、エフェクトの一覧・パラメータ・フレーム生成をここに集約し、
両タブは effect_ui.EffectSettingsPanel を通してこのモジュールだけを見る。

【最重要：保存される値は「内部キー」】
設定ファイル(config.json)と配布パックの oreHighlighterProject.json に保存されるのは、
表示名ではなく下の内部キー（"rainbow_outline" など）。表示名はいつでも自由に
変えてよいが、内部キーは絶対にリネームしないこと（過去に保存されたデータが読めなくなる）。

過去のバージョンは表示名そのものを保存していたため、LEGACY_NAME_TO_KEY で
内部キーへ読み替える。読み込み時は必ず normalize_effect() を通すこと。

Copyright (c) 2026 旬茶
Licensed under the MIT License.
"""

from texture_effects import (
    rainbow_frames, blink_frames, outline_frames, outline_rainbow_frames,
    rainbow_and_outline_frames, rainbow_gradient_frames,
)

# --- 内部キー（設定ファイルに保存される値。絶対にリネームしないこと） ---
NONE = "none"
RAINBOW_OUTLINE = "rainbow_outline"
RAINBOW = "rainbow"
RAINBOW_GRADIENT = "rainbow_gradient"
OUTLINE = "outline"
OUTLINE_RAINBOW = "outline_rainbow"
BLINK = "blink"

# --- 表示名（UIに出る文字列。内部キーと分離してあるので自由に変更してよい） ---
DISPLAY_NAMES = {
    NONE: "なし（静止画）",
    RAINBOW_OUTLINE: "レインボー＋枠線",
    RAINBOW: "レインボー",
    RAINBOW_GRADIENT: "レインボー（斜めグラデ）",
    OUTLINE: "枠線",
    OUTLINE_RAINBOW: "枠線（レインボー）",
    BLINK: "点滅",
}

# ブロックは必ず何らかのエフェクトを付ける前提なので「なし」を持たない。
BLOCK_EFFECT_KEYS = [
    RAINBOW_OUTLINE, RAINBOW, RAINBOW_GRADIENT, OUTLINE, OUTLINE_RAINBOW, BLINK,
]
# アイテムは「外部PNGに差し替えるだけでエフェクトは付けない」があり得るので「なし」を持つ。
ITEM_EFFECT_KEYS = [NONE] + BLOCK_EFFECT_KEYS

# --- 旧バージョンが保存していた表示名 → 内部キー ---
# ブロック側とアイテム側で表記が違ったものも、同じ内部キーに寄せる。
LEGACY_NAME_TO_KEY = {
    # ブロックエフェクトタブの旧表示名
    "レインボー + 枠線": RAINBOW_OUTLINE,
    "レインボーのみ": RAINBOW,
    "レインボーのみ（斜めグラデーション）": RAINBOW_GRADIENT,
    "枠線のみ": OUTLINE,
    "枠線のみ（レインボー）": OUTLINE_RAINBOW,
    "点滅": BLINK,
    # アイテムテクスチャ編集タブの旧表示名（「レインボーのみ」「点滅」は共通）
    "なし（静止画のみ）": NONE,
    "レインボー（斜めグラデーション）": RAINBOW_GRADIENT,
}

# 表示名→キーの逆引き（現行の表示名が保存されていた場合の保険）
_DISPLAY_TO_KEY = {name: key for key, name in DISPLAY_NAMES.items()}

# --- パラメータの既定値（ブロック・アイテム共通） ---
DEFAULT_EFFECT_SETTINGS = {
    "frame_count": 16,
    "frametime": 2,
    "thickness": 1,
    "border_saturation": 0.7,
    "border_brightness": 0.7,
    "dark_factor": 0.35,
    "border_color": "#ff3c3c",     # 「枠線」（固定色）の枠線色。#RRGGBB形式
    "gradient_band_count": 3,      # 「レインボー（斜めグラデ）」の帯の本数
    "gradient_transparency": 0.4,  # 同上。虹色に元の絵をどれだけ透けさせるか(0=不透明, 1=元の絵そのまま)
}

DEFAULT_BLOCK_SETTINGS = dict(DEFAULT_EFFECT_SETTINGS, effect=RAINBOW_OUTLINE)
DEFAULT_ITEM_SETTINGS = dict(DEFAULT_EFFECT_SETTINGS, effect=NONE)

# --- どのエフェクトがどのパラメータを使うか（UIの有効/無効の判定に使う） ---
USES_FRAME_COUNT = {RAINBOW_OUTLINE, RAINBOW, RAINBOW_GRADIENT, OUTLINE_RAINBOW}
USES_THICKNESS = {RAINBOW_OUTLINE, OUTLINE, OUTLINE_RAINBOW}
# 枠線の色を「毎フレームの色相」から自動計算する＝彩度・明るさで調整するもの
USES_BORDER_HSV = {RAINBOW_OUTLINE, OUTLINE_RAINBOW}
# 枠線の色が変化しない＝固定色を選ぶもの
USES_BORDER_COLOR = {OUTLINE}
USES_GRADIENT = {RAINBOW_GRADIENT}
USES_DARK_FACTOR = {BLINK}


def normalize_effect(value, default=None):
    """保存されていた effect の値を内部キーに正規化する。

    受け付けるもの:
      - 内部キー（現行）
      - 旧バージョンの表示名（ブロック側・アイテム側どちらの表記でも可）
      - 現行の表示名（保険）
    どれにも当てはまらなければ default を返す。
    """
    if value in DISPLAY_NAMES:
        return value
    if value in LEGACY_NAME_TO_KEY:
        return LEGACY_NAME_TO_KEY[value]
    if value in _DISPLAY_TO_KEY:
        return _DISPLAY_TO_KEY[value]
    return default


def normalize_settings(settings, default_effect):
    """設定辞書の "effect" をその場で内部キーに直す（辞書自体を返す）。
    デフォルトとのマージ直後に必ず通すこと。"""
    settings["effect"] = normalize_effect(settings.get("effect"), default=default_effect)
    return settings


def display_name(key):
    return DISPLAY_NAMES.get(key, key)


def hex_to_rgba(hex_color, alpha=255):
    """"#RRGGBB" 形式の文字列を (r, g, b, a) タプルにする。
    不正な値なら既定の枠線色にフォールバックする（設定ファイルが壊れていても落ちないように）。"""
    value = (hex_color or "").lstrip("#")
    if len(value) != 6:
        value = DEFAULT_EFFECT_SETTINGS["border_color"].lstrip("#")
    try:
        r = int(value[0:2], 16)
        g = int(value[2:4], 16)
        b = int(value[4:6], 16)
    except ValueError:
        r, g, b = 255, 60, 60
    return (r, g, b, alpha)


def rgb_to_hex(r, g, b):
    return "#{:02x}{:02x}{:02x}".format(r, g, b)


def generate_frames(image, settings):
    """設定辞書に従ってアニメーションの各フレーム画像を作る。
    ブロック・アイテムのどちらからも同じ関数を使う（以前は別実装だった）。"""
    key = normalize_effect(settings.get("effect"), default=NONE)

    def p(name):
        return settings.get(name, DEFAULT_EFFECT_SETTINGS[name])

    if key == RAINBOW_OUTLINE:
        return rainbow_and_outline_frames(
            image,
            frame_count=p("frame_count"),
            thickness=p("thickness"),
            border_saturation=p("border_saturation"),
            border_brightness=p("border_brightness"),
        )
    if key == RAINBOW:
        return rainbow_frames(image, frame_count=p("frame_count"))
    if key == RAINBOW_GRADIENT:
        return rainbow_gradient_frames(
            image,
            frame_count=p("frame_count"),
            band_count=p("gradient_band_count"),
            reverse=True,  # 右下→左上方向（ユーザー要望の向き）
            pattern_visibility=p("gradient_transparency"),
        )
    if key == OUTLINE:
        return outline_frames(
            image,
            color=hex_to_rgba(p("border_color")),
            thickness=p("thickness"),
            frame_count=2,
        )
    if key == OUTLINE_RAINBOW:
        return outline_rainbow_frames(
            image,
            frame_count=p("frame_count"),
            thickness=p("thickness"),
            border_saturation=p("border_saturation"),
            border_brightness=p("border_brightness"),
        )
    if key == BLINK:
        return blink_frames(image, frame_count=2, dark_factor=p("dark_factor"))
    return [image]
