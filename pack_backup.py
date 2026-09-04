"""
リソースパックのバックアップ書き出しに関する共通処理（UIダイアログを含む）。

【なぜこのモジュールがあるか】
「既存プロジェクトを開く」（ブロックエフェクトタブ）と「既存パックからGUIアイコンを
読み込む」（GUIアイコン編集タブ）は、どちらも読み込み前に今の内容をバックアップとして
書き出せる。この一連の流れが両タブでほぼ同一のコードとして二重に実装されており、
文言の主語（「対象ブロック…」／「保存済みのバリアント」）だけが違う状態だった:

  _ask_import_mode        / _ask_project_import_mode
  _ask_backup_save_mode   / _ask_project_backup_save_mode
  _do_backup_export       / _do_project_backup_export
  _on_open_backup_folder  / _on_open_project_backup_folder

片方だけ直して片方が古いまま、という事故を防ぐためここに一本化した。
違うのは「実際に何を書き出すか」だけなので、そこは write_pack コールバックで渡す。

なおzip化は、以前はブロックタブ側だけが安全な実装（一時ファイルに書き切ってから
os.replaceで差し替え）を持っていた。共通化により、GUIアイコンのバックアップも
同じ安全なzip化を通るようになっている。

Copyright (c) 2026 旬茶
Licensed under the MIT License.
"""

import datetime
import os
import shutil
import zipfile

from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtCore import QUrl


def ask_import_mode(parent, text):
    """読み込み前に今の内容をどうするか3択で聞く。
    戻り値: "backup_then_replace" / "merge" / "replace" / None(キャンセル)"""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle("読み込み方法の選択")
    box.setText(text)
    backup_btn = box.addButton("保存してから読み込む", QMessageBox.ButtonRole.AcceptRole)
    merge_btn = box.addButton("既存データを残したまま読み込む（マージ）", QMessageBox.ButtonRole.AcceptRole)
    replace_btn = box.addButton("全部置き換える", QMessageBox.ButtonRole.DestructiveRole)
    cancel_btn = box.addButton("キャンセル", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(cancel_btn)
    box.exec()
    clicked = box.clickedButton()
    if clicked is backup_btn:
        return "backup_then_replace"
    if clicked is merge_btn:
        return "merge"
    if clicked is replace_btn:
        return "replace"
    return None


def ask_backup_save_mode(parent, text):
    """バックアップを別名で残すか上書きするかを聞く。
    戻り値: "rename" / "overwrite" / None(キャンセル)"""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle("バックアップの保存方法")
    box.setText(text)
    rename_btn = box.addButton("別名で保存（日付を付けて両方残す）", QMessageBox.ButtonRole.AcceptRole)
    overwrite_btn = box.addButton("上書き（同じパック名で既存を置き換え）", QMessageBox.ButtonRole.AcceptRole)
    cancel_btn = box.addButton("キャンセル", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(cancel_btn)
    box.exec()
    clicked = box.clickedButton()
    if clicked is rename_btn:
        return "rename"
    if clicked is overwrite_btn:
        return "overwrite"
    return None


def backup_pack_name(pack_name, save_mode):
    """"rename" なら日付を足した名前、"overwrite" ならそのままの名前を返す。"""
    if save_mode == "rename":
        return f"{pack_name}_{datetime.date.today().isoformat()}"
    return pack_name


def zip_pack_folder(pack_root):
    """
    pack_root フォルダの中身を pack_root + '.zip' にまとめ、フォルダ自体は削除する
    （Minecraft はzipのままリソースパックとして読み込めるため）。
    zip内はpack.mcmetaがルート直下に来るよう、pack_root相対のパスで格納する。

    いきなり本番のzipを上書きせず、一時ファイル（.zip.tmp）に書き切ってから
    差し替える。こうしておくと、書き込み中にディスクが一杯になったり、
    Minecraftがzipを掴んでいて置き換えられなかった場合でも、
    前回生成したzipが壊れずにそのまま残る。
    """
    zip_path = pack_root + ".zip"
    tmp_zip_path = pack_root + ".zip.tmp"
    if os.path.exists(tmp_zip_path):
        os.remove(tmp_zip_path)
    try:
        with zipfile.ZipFile(tmp_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _dirs, files in os.walk(pack_root):
                for fn in files:
                    full = os.path.join(root, fn)
                    arcname = os.path.relpath(full, pack_root)
                    zf.write(full, arcname)
        # os.replace は同名ファイルがあっても上書きできる（Windows/Mac/Linux共通）
        os.replace(tmp_zip_path, zip_path)
    except Exception:
        if os.path.exists(tmp_zip_path):
            try:
                os.remove(tmp_zip_path)
            except OSError:
                pass
        raise
    shutil.rmtree(pack_root)
    return zip_path


def run_backup_export(parent, *, has_content, pack_name, output_dir, write_pack,
                      confirm_text, missing_output_message, on_success,
                      error_hint=""):
    """
    バックアップ書き出しの共通フロー。「続行してよいか」を bool で返す。

      1. 書き出す中身が無ければ、何もせず True（バックアップ不要なので続行してよい）
      2. 出力先が未設定なら警告して False
      3. 保存方法（別名／上書き）を聞く。キャンセルなら False
      4. write_pack(pack_root) を呼ぶ。失敗したらエラーを出して False
      5. 成功したら on_success(zip_path, write_packの戻り値) を呼んで True

    write_pack は「pack_root にパックを書き出し、zip化してフォルダを消す」ところまでを行う
    （zip化には zip_pack_folder() を使うこと）。何を書き出すかだけが呼び出し側の違いなので、
    ここには含めない。
    """
    if not has_content:
        return True

    if not output_dir:
        QMessageBox.warning(parent, "出力先未設定", missing_output_message)
        return False

    save_mode = ask_backup_save_mode(parent, confirm_text)
    if save_mode is None:
        return False

    pack_root = os.path.join(output_dir, backup_pack_name(pack_name, save_mode))
    try:
        result = write_pack(pack_root)
    except Exception as e:
        QMessageBox.critical(parent, "エラー", f"バックアップの保存に失敗しました: {e}{error_hint}")
        return False

    # pack_root フォルダはzip化後に削除されているので、
    # 「開く」ボタンはzipが入っている親フォルダ(出力先)を指すようにする。
    on_success(pack_root + ".zip", result)
    return True


def open_backup_folder(parent, backup_dir):
    """バックアップの保存先フォルダをOSのファイラで開く。"""
    del parent  # QDesktopServices は親を必要としないが、呼び出し側の対称性のため受け取る
    if backup_dir and os.path.isdir(backup_dir):
        QDesktopServices.openUrl(QUrl.fromLocalFile(backup_dir))
