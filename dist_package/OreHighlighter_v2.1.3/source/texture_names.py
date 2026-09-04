"""
ブロックテクスチャのファイル名（拡張子なし）から日本語名を引くための対応表。

鉱石ハイライト用途で使われやすい鉱石・鉱石ブロック・周辺の一般的な岩石系ブロックを中心に収録。
未収録のファイル名は get_block_jp_name() が None を返す（呼び出し側でファイル名のみ表示にフォールバックする）。

収録漏れを見つけたら、この辞書に追記するだけで一覧・編集中ラベル双方に反映される。

Copyright (c) 2026 旬茶
Licensed under the MIT License. 詳細は同梱の LICENSE ファイルを参照してください。
"""

BLOCK_NAME_JA = {
    # ---- 鉱石（オーバーワールド） ----
    "coal_ore": "石炭鉱石",
    "iron_ore": "鉄鉱石",
    "copper_ore": "銅鉱石",
    "gold_ore": "金鉱石",
    "redstone_ore": "レッドストーン鉱石",
    "lapis_ore": "ラピスラズリ鉱石",
    "diamond_ore": "ダイヤモンド鉱石",
    "emerald_ore": "エメラルド鉱石",

    # ---- 鉱石（深層岩） ----
    "deepslate_coal_ore": "深層石炭鉱石",
    "deepslate_iron_ore": "深層鉄鉱石",
    "deepslate_copper_ore": "深層銅鉱石",
    "deepslate_gold_ore": "深層金鉱石",
    "deepslate_redstone_ore": "深層レッドストーン鉱石",
    "deepslate_lapis_ore": "深層ラピスラズリ鉱石",
    "deepslate_diamond_ore": "深層ダイヤモンド鉱石",
    "deepslate_emerald_ore": "深層エメラルド鉱石",

    # ---- 鉱石（ネザー） ----
    "nether_gold_ore": "ネザー金鉱石",
    "nether_quartz_ore": "ネザークォーツ鉱石",
    "ancient_debris_side": "古代の残骸（側面）",
    "ancient_debris_top": "古代の残骸（上面）",

    # ---- 未加工鉱物ブロック ----
    "raw_iron_block": "鉄の原石ブロック",
    "raw_gold_block": "金の原石ブロック",
    "raw_copper_block": "銅の原石ブロック",

    # ---- 鉱物ブロック ----
    "iron_block": "鉄ブロック",
    "gold_block": "金ブロック",
    "diamond_block": "ダイヤモンドブロック",
    "emerald_block": "エメラルドブロック",
    "lapis_block": "ラピスラズリブロック",
    "redstone_block": "レッドストーンブロック",
    "coal_block": "石炭ブロック",
    "copper_block": "銅ブロック",
    "exposed_copper": "露出した銅ブロック",
    "weathered_copper": "風化した銅ブロック",
    "oxidized_copper": "酸化した銅ブロック",
    "netherite_block": "ネザライトブロック",

    # ---- アメジスト ----
    "amethyst_block": "アメジストブロック",
    "budding_amethyst": "アメジスト晶洞ブロック",

    # ---- 発掘（考古学）系 ----
    "suspicious_sand_0": "怪しい砂（発掘前）",
    "suspicious_sand_1": "怪しい砂（発掘中1）",
    "suspicious_sand_2": "怪しい砂（発掘中2）",
    "suspicious_sand_3": "怪しい砂（発掘完了）",
    "suspicious_gravel_0": "怪しい砂利（発掘前）",
    "suspicious_gravel_1": "怪しい砂利（発掘中1）",
    "suspicious_gravel_2": "怪しい砂利（発掘中2）",
    "suspicious_gravel_3": "怪しい砂利（発掘完了）",

    # ---- 一般的な岩石・地形ブロック（鉱石の周辺に出やすいもの） ----
    "stone": "石",
    "cobblestone": "丸石",
    "mossy_cobblestone": "苔むした丸石",
    "deepslate": "深層岩",
    "cobbled_deepslate": "深層岩の丸石",
    "polished_deepslate": "磨かれた深層岩",
    "chiseled_deepslate": "模様入り深層岩",
    "deepslate_bricks": "深層岩レンガ",
    "deepslate_tiles": "深層岩タイル",
    "granite": "花崗岩",
    "diorite": "閃緑岩",
    "andesite": "安山岩",
    "polished_granite": "磨かれた花崗岩",
    "polished_diorite": "磨かれた閃緑岩",
    "polished_andesite": "磨かれた安山岩",
    "tuff": "凝灰岩",
    "calcite": "方解石",
    "dripstone_block": "鍾乳石ブロック",
    "netherrack": "ネザーラック",
    "blackstone": "ブラックストーン",
    "gilded_blackstone": "金核入りブラックストーン",
    "basalt_side": "玄武岩（側面）",
    "basalt_top": "玄武岩（上面）",
    "smooth_basalt": "滑らかな玄武岩",
    "end_stone": "エンドストーン",
    "obsidian": "黒曜石",
    "crying_obsidian": "泣く黒曜石",
    "bedrock": "岩盤",
    "sandstone": "砂岩",
    "red_sandstone": "赤い砂岩",
    "sand": "砂",
    "red_sand": "赤い砂",
    "gravel": "砂利",
    "dirt": "土",
    "coarse_dirt": "粗い土",
    "grass_block_top": "草ブロック（上面）",
    "grass_block_side": "草ブロック（側面）",
    "podzol_top": "ポドゾル（上面）",
    "mycelium_top": "菌糸（上面）",
    "clay": "粘土",
    "magma": "マグマブロック",
    "glowstone": "グロウストーン",
    "quartz_block_side": "クォーツブロック（側面）",
    "quartz_block_top": "クォーツブロック（上面）",
}


def block_jp_name(filename: str):
    """
    'diamond_ore.png' のようなファイル名（拡張子ありなし両対応）から日本語名を返す。
    未収録の場合は None を返す。
    """
    if filename is None:
        return None
    base = filename[:-4] if filename.lower().endswith(".png") else filename
    return BLOCK_NAME_JA.get(base)
