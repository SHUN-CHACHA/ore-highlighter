"""
配布用パッケージ作成スクリプト。

やること:
  1. PyInstaller で main.py を単体exe化する（Windows上で実行した場合のみ .exe が作られる）
  2. exe と、Pythonソース一式（.py）・LICENSE・README・使用マニュアルをひとつのフォルダにまとめる
  3. そのフォルダをzip化する（配布用の1ファイル）

前提:
  pip install pyinstaller

使い方（Windows上のこのフォルダで）:
  python build_and_package.py

出力:
  dist_package/OreHighlighter_vX.Y.Z.zip
  中身:
    OreHighlighter_vX.Y.Z.exe   … 本体（これだけで動く）
    LICENSE / README.md / 使用マニュアル.html
    source/                     … 改造したい人向けのソース一式（SOURCE_FILES）
    source/tests/               … テスト一式（python tests/run_tests.py で実行）

  ソースの追加・削除をしたら SOURCE_FILES も更新してください。
  （exe化自体はimportを辿って自動で取り込まれるので、SOURCE_FILESの漏れでは
  　exeは壊れません。zipに.pyが同梱されないだけで気づきにくいので注意）

注意:
  PyInstallerは「実行しているOS向け」のexeしか作れません（クロスコンパイル不可）。
  Windows用のexeが欲しい場合は、必ずWindows上でこのスクリプトを実行してください。
  Windows以外（Mac/Linux）で実行した場合は、exeの代わりにそのOS用の実行ファイルが作られます。
"""

import os
import shutil
import subprocess
import sys
import time
import zipfile

APP_NAME = "OreHighlighter"
VERSION = "2.1.3"  # リリースごとに更新してください
EXE_NAME = f"{APP_NAME}_v{VERSION}"  # exeファイル自体の名前にもバージョンを含める
ICON_FILE = "icon.ico"

HERE = os.path.dirname(os.path.abspath(__file__))

# exe化に含めるソースファイル一式（zipにはそのままの.pyとしても同梱する）
SOURCE_FILES = [
    "main.py",
    "block_tab.py",
    "gui_icon_editor.py",
    "item_texture_editor.py",
    "source_tab.py",
    "effect_catalog.py",
    "pack_backup.py",
    "pixel_editor.py",
    "list_ui.py",
    "effect_ui.py",
    "ui_utils.py",
    "texture_effects.py",
    "texture_names.py",
    "launcher_scan.py",
    "icon.ico",
]

# source/ の中にフォルダごとコピーするもの（存在するものだけ同梱される）
SOURCE_DIRS = [
    "tests",
]

# 一緒に同梱するドキュメント類（存在するものだけ同梱される）
EXTRA_FILES = [
    "LICENSE",
    "README.md",
    "使用マニュアル.html",
]


def run_pyinstaller():
    print("== PyInstaller でexe化しています... ==")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--noconsole",
        "--name", EXE_NAME,
    ]

    icon_path = os.path.join(HERE, ICON_FILE)
    if os.path.exists(icon_path):
        # --icon: エクスプローラーで見えるexeファイル自体のアイコン
        cmd += ["--icon", icon_path]
        # --add-data: exe内部にicon.icoを同梱し、実行中のウィンドウ/タスクバーアイコンにも使う
        # （Windowsは区切りが ";"、Mac/Linuxは ":"）
        cmd += ["--add-data", f"{icon_path}{os.pathsep}."]
    else:
        print(f"警告: {ICON_FILE} が見つからないため、アイコン無しでビルドします。")

    cmd += ["main.py"]
    subprocess.run(cmd, check=True, cwd=HERE)


def rmtree_with_retry(path, retries=5, delay_seconds=1.0):
    """
    shutil.rmtree のリトライ版。

    Windowsでは、ビルド直後のexeをウイルス対策ソフトがスキャン中だったり、
    エクスプローラーでそのフォルダを開いていたりすると、削除しようとした
    瞬間だけ PermissionError (WinError 5) になることがある。多くの場合は
    数秒でロックが外れるので、そのまま失敗させず少し待って再試行する。
    """
    if not os.path.exists(path):
        return
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            shutil.rmtree(path)
            return
        except (PermissionError, OSError) as e:
            last_error = e
            if attempt < retries:
                print(
                    f"「{path}」の削除に失敗しました（{attempt}/{retries}回目）。"
                    f"ウイルス対策ソフトのスキャン中か、エクスプローラーで開かれている"
                    f"可能性があります。{delay_seconds}秒待って再試行します..."
                )
                time.sleep(delay_seconds)
    raise RuntimeError(
        f"「{path}」を削除できませんでした（{retries}回試行）。\n"
        f"考えられる原因: ウイルス対策ソフトがexeをスキャン中 / エクスプローラーで"
        f"フォルダやファイルを開いている / 前回ビルドしたexeを実行中。\n"
        f"該当のフォルダやexeを閉じてから、もう一度実行してください。\n"
        f"元のエラー: {last_error}"
    ) from last_error


def find_built_executable():
    dist_dir = os.path.join(HERE, "dist")
    candidates = [
        os.path.join(dist_dir, f"{EXE_NAME}.exe"),  # Windows
        os.path.join(dist_dir, EXE_NAME),           # Mac/Linux
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    raise FileNotFoundError(
        f"ビルド後の実行ファイルが見つかりません（{dist_dir} を確認してください）"
    )


def build_package_folder():
    exe_path = find_built_executable()

    package_name = f"{APP_NAME}_v{VERSION}"
    out_root = os.path.join(HERE, "dist_package")
    package_dir = os.path.join(out_root, package_name)

    rmtree_with_retry(package_dir)
    os.makedirs(package_dir)

    # exe（またはOS実行ファイル）をコピー
    # ビルド直後はここでもウイルス対策ソフトにロックされていることがあるため、
    # コピー自体もリトライする。
    dest_exe = os.path.join(package_dir, os.path.basename(exe_path))
    last_error = None
    for attempt in range(1, 6):
        try:
            shutil.copy2(exe_path, dest_exe)
            break
        except (PermissionError, OSError) as e:
            last_error = e
            print(
                f"exeのコピーに失敗しました（{attempt}/5回目）。"
                f"少し待って再試行します..."
            )
            time.sleep(1.0)
    else:
        raise RuntimeError(
            f"「{exe_path}」をコピーできませんでした。\n"
            f"ウイルス対策ソフトのスキャンが終わるのを待ってから、"
            f"もう一度実行してください。\n元のエラー: {last_error}"
        ) from last_error

    # Pythonソース一式をコピー（改造したい人向け）
    src_dir = os.path.join(package_dir, "source")
    os.makedirs(src_dir, exist_ok=True)
    for fn in SOURCE_FILES:
        src = os.path.join(HERE, fn)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(src_dir, fn))
        else:
            print(f"警告: SOURCE_FILES の「{fn}」が見つからないため同梱をスキップします。")

    # tests/ などのフォルダを丸ごとコピー（__pycache__ は除く）
    for dn in SOURCE_DIRS:
        src = os.path.join(HERE, dn)
        if os.path.isdir(src):
            shutil.copytree(
                src, os.path.join(src_dir, dn),
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )

    # LICENSE・README・マニュアル類をコピー
    for fn in EXTRA_FILES:
        src = os.path.join(HERE, fn)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(package_dir, fn))

    return package_dir


def zip_package(package_dir):
    zip_path = package_dir + ".zip"
    if os.path.exists(zip_path):
        os.remove(zip_path)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(package_dir):
            for fn in files:
                full = os.path.join(root, fn)
                arcname = os.path.relpath(full, os.path.dirname(package_dir))
                zf.write(full, arcname)

    return zip_path


def main():
    run_pyinstaller()
    package_dir = build_package_folder()
    zip_path = zip_package(package_dir)
    print("== 完了 ==")
    print(f"配布用zip: {zip_path}")


if __name__ == "__main__":
    main()
