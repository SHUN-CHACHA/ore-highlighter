"""
公式ランチャー・Prism Launcherの検索まわりの純粋関数。

main.py の OreHighlighterWindow（UI）とは無関係に、ファイルシステムだけを見て
結果を返す関数だけを集めている。UIの状態（self.xxx）には一切触れないので、
単体でテストしやすく、他のUIコードから安全に呼び出せる。

Copyright (c) 2026 旬茶
Licensed under the MIT License. 詳細は同梱の LICENSE ファイルを参照してください。
"""

import os
import sys
import string


def _prism_search_roots():
    roots = []
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        localappdata = os.environ.get("LOCALAPPDATA")
        if appdata:
            roots.append(os.path.join(appdata, "PrismLauncher"))
        if localappdata:
            roots.append(os.path.join(localappdata, "PrismLauncher"))
        for letter in string.ascii_uppercase:
            drive = f"{letter}:\\"
            if os.path.exists(drive):
                roots.append(os.path.join(drive, "PrismLauncher"))
    else:
        home = os.path.expanduser("~")
        roots.append(os.path.join(home, ".local", "share", "PrismLauncher"))
        roots.append(os.path.join(home, "Library", "Application Support", "PrismLauncher"))
    return roots


def find_prism_instances(extra_roots=None):
    roots = list(extra_roots) if extra_roots else []
    roots += _prism_search_roots()

    results = []
    seen = set()
    for root in roots:
        instances_dir = os.path.join(root, "instances")
        if not os.path.isdir(instances_dir):
            continue
        try:
            names = os.listdir(instances_dir)
        except OSError:
            continue
        for name in names:
            inst_path = os.path.join(instances_dir, name)
            mc_path = os.path.join(inst_path, "minecraft")
            if not os.path.isdir(mc_path):
                mc_path = os.path.join(inst_path, ".minecraft")
            if os.path.isdir(mc_path) and mc_path not in seen:
                seen.add(mc_path)
                results.append((name, mc_path))
    return results


def find_launcher_jars(root):
    """
    公式ランチャーの .minecraft フォルダ、または Prism Launcher のルートフォルダ
    （instances フォルダがある場所）を渡すと、中の各バージョンjarを探して
    [(表示名, jarのフルパス), ...] を返す。

    対応パターン:
      - root 自体が .minecraft 相当（直下に versions フォルダがある。公式ランチャー形式）
      - root が Prism Launcher のルート（直下に libraries/com/mojang/minecraft がある。
        実機確認済み：Prismは全インスタンス共有のライブラリキャッシュに実体jarを置き、
        minecraft-<version>-client.jar というファイル名になる。インスタンスごとの
        minecraft/versions フォルダには実体が無い場合がある）
      - root が Prismの特定インスタンスの minecraft(.minecraft) フォルダそのもの
        （直下に versions フォルダがある。公式形式のインスタンスの場合）
      - root自体が「com/mojang/minecraft」フォルダ、またはバージョンフォルダそのものを
        直接指定した場合の救済パターン
    見つからなければ空リストを返す（呼び出し側でエラー扱いにはしない）。
    """
    results = []
    seen_paths = set()

    def add(label, jar_path):
        if jar_path not in seen_paths and os.path.isfile(jar_path):
            seen_paths.add(jar_path)
            results.append((label, jar_path))

    def scan_versions_dir(versions_dir, label_prefix=""):
        # 公式ランチャー形式: <versions_dir>/<name>/<name>.jar
        if not os.path.isdir(versions_dir):
            return
        try:
            names = sorted(os.listdir(versions_dir))
        except OSError:
            return
        for name in names:
            add(f"{label_prefix}{name}", os.path.join(versions_dir, name, f"{name}.jar"))

    def scan_prism_shared_libs(lib_dir, label_prefix=""):
        # Prism Launcherの共有ライブラリキャッシュ形式:
        # <lib_dir>/<version>/minecraft-<version>-client.jar
        if not os.path.isdir(lib_dir):
            return
        try:
            ver_names = sorted(os.listdir(lib_dir))
        except OSError:
            return
        for v in ver_names:
            add(f"{label_prefix}{v}", os.path.join(lib_dir, v, f"minecraft-{v}-client.jar"))

    # パターン1: root自体が .minecraft 相当（versionsフォルダを直接持つ）
    scan_versions_dir(os.path.join(root, "versions"))

    # パターン2: root が Prism Launcher のルート（共有ライブラリキャッシュ）
    scan_prism_shared_libs(os.path.join(root, "libraries", "com", "mojang", "minecraft"))

    # パターン3: root が Prism Launcher のルート（instancesフォルダを持つ、公式形式インスタンス救済）
    instances_dir = os.path.join(root, "instances")
    if os.path.isdir(instances_dir):
        try:
            inst_names = sorted(os.listdir(instances_dir))
        except OSError:
            inst_names = []
        for inst_name in inst_names:
            inst_path = os.path.join(instances_dir, inst_name)
            for mc_name in ("minecraft", ".minecraft"):
                scan_versions_dir(
                    os.path.join(inst_path, mc_name, "versions"),
                    label_prefix=f"{inst_name} / ",
                )

    # パターン4: root自体が「com/mojang/minecraft」フォルダそのものを指定した場合の救済
    scan_prism_shared_libs(root)

    # パターン5: root自体が特定バージョンフォルダそのもの
    # （例: .../libraries/com/mojang/minecraft/26.1）を直接指定した場合の救済
    base_name = os.path.basename(os.path.normpath(root))
    add(base_name, os.path.join(root, f"minecraft-{base_name}-client.jar"))

    return results
