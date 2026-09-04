# テストの実行方法

```
python tests/run_tests.py
```

追加インストールは不要です（標準の unittest のみ使用）。PyQt6 と Pillow が入っていれば動きます。

個別に実行する場合:

```
python -m unittest tests.test_pack_failure -v
```

画面の無い環境でも動くよう、`helpers.py` が `QT_QPA_PLATFORM=offscreen` を設定します。ウィンドウは表示されません。

## 何を守っているか

| ファイル | 守っている挙動 |
|---|---|
| `test_config.py` | config.json のキー構成（過去バージョンとの互換）と、保存→読み込みの往復 |
| `test_pack_generation.py` | zip出力・フォルダを残さないこと・`path` キーを埋め込まないこと |
| `test_pack_failure.py` | 生成に失敗しても作りかけを残さず、前回のパックを壊さないこと（v1.2.4の修正） |
| `test_block_tab.py` | 読み込み・追加・エフェクト編集・削除と取り消し・フィルタ |
| `test_host_binding.py` | `bind_host()` の結線（他タブ参照・ビジーダイアログ・サマリー更新） |
| `test_drag_and_drop.py` | タブと拡張子による D&D の振り分け |

いずれも「起動テストでは気づけない」種類の壊れ方を対象にしています。実際に、修正前のコードへ意図的に戻すと該当テストが失敗することを確認済みです。

## テストを書くときの注意（過去にハマった罠）

**1. ダミー画像に偽PNGを使わない**

`b"x"` のような1バイトのファイルを PNG のつもりで置くと、PIL の挙動が不安定になります。`create_placeholder_ore_texture()` で本物の PNG を作ってください（`helpers.make_texture_folder()` がやっています）。

**2. Undo のテストは本物のマウスイベントで**

`canvas.pixels[y][x] = ...` と直接書き換えると、`mousePressEvent` 経由の Undo 追跡をバイパスします。Undo 関連を検証するときは実際の `QMouseEvent` を発行してください。

**3. ダイアログのモックは2種類ある**

`QMessageBox.question` などの静的メソッドを潰すだけでは、`box.exec()` を使う実装（未保存確認・読み込み方法の選択など）は止まりません。そちらを通るテストでは `helpers.silence_exec()` も併用してください。

**4. `AUTO_CONFIG_PATH` を必ず差し替える**

`OreHighlighterWindow()` は起動時に `APP_DIR/config.json` を自動で読み込みます。差し替えずにテストすると、開発中の本物の設定を読んでしまい結果が環境依存になります。`helpers.make_window()` が一時ファイルへ向け直しているので、ウィンドウ生成には必ずこれを使ってください。

**5. `QApplication` はプロセスに1つだけ**

`helpers.get_app()` が使い回します。テストごとに作り直さないでください。

## 追加するときは

`tests/test_*.py` に置けば `run_tests.py` が自動で拾います。先頭で必ず `helpers` を PyQt6 より先に import してください（offscreen 設定と import パス追加を行っているため）。
