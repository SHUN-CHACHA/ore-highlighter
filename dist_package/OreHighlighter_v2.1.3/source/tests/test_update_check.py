"""
起動時のバージョン更新確認機能のテスト。

対象:
  - main.py の is_newer_version() / _parse_version_tuple()（純粋関数）
  - OreHighlighterWindow._show_update_banner() / _dismiss_update_banner()
  - OreHighlighterWindow._on_update_check_finished()（実際のネットワークは使わず、
    FakeReplyで様々な応答パターンを再現する）
  - OreHighlighterWindow._check_for_updates() が例外を投げずに呼べること（スモークテスト）
  - ウィンドウタイトルにアプリ名とバージョンが含まれること

実際のGitHub APIへは一切アクセスしない（テスト環境はネットワーク遮断されている
ことがあるため、FakeReplyで全パターンをオフラインに再現する）。
"""

import json
import unittest

from helpers import make_window, get_app
import main as M
from PyQt6.QtNetwork import QNetworkReply


class FakeReply:
    """QNetworkReplyの代わりに使う、テスト用の最小限のダミー。"""

    def __init__(self, body: bytes = b"", error=QNetworkReply.NetworkError.NoError):
        self._body = body
        self._error = error
        self.delete_called = False

    def error(self):
        return self._error

    def readAll(self):
        return self._body

    def deleteLater(self):
        self.delete_called = True


class TestVersionComparison(unittest.TestCase):
    def test_newer_patch_version_is_detected(self):
        self.assertTrue(M.is_newer_version("v2.1.3", "2.1.2"))

    def test_newer_minor_version_is_detected(self):
        self.assertTrue(M.is_newer_version("v2.2.0", "2.1.2"))

    def test_newer_major_version_is_detected(self):
        self.assertTrue(M.is_newer_version("v3.0.0", "2.1.2"))

    def test_same_version_is_not_newer(self):
        self.assertFalse(M.is_newer_version("v2.1.2", "2.1.2"))

    def test_older_version_is_not_newer(self):
        self.assertFalse(M.is_newer_version("v2.1.0", "2.1.2"))

    def test_leading_v_is_optional_on_either_side(self):
        self.assertTrue(M.is_newer_version("2.1.3", "v2.1.2"))

    def test_unparseable_remote_version_is_not_treated_as_newer(self):
        self.assertFalse(M.is_newer_version("not-a-version", "2.1.2"))

    def test_unparseable_current_version_is_not_treated_as_older(self):
        self.assertFalse(M.is_newer_version("v2.1.3", "not-a-version"))


class TestUpdateBanner(unittest.TestCase):
    def setUp(self):
        self.win = make_window()

    def tearDown(self):
        self.win.close()

    def test_banner_is_created_when_shown(self):
        self.assertIsNone(self.win._update_banner)
        self.win._show_update_banner("v9.9.9", "https://example.invalid/release")
        self.assertIsNotNone(self.win._update_banner)

    def test_banner_is_not_duplicated_on_repeated_calls(self):
        self.win._show_update_banner("v9.9.9", "https://example.invalid/release")
        first = self.win._update_banner
        self.win._show_update_banner("v9.9.9", "https://example.invalid/release")
        self.assertIs(self.win._update_banner, first)

    def test_dismiss_clears_the_banner(self):
        self.win._show_update_banner("v9.9.9", "https://example.invalid/release")
        self.win._dismiss_update_banner()
        self.assertIsNone(self.win._update_banner)

    def test_dismiss_without_a_banner_does_not_raise(self):
        self.win._dismiss_update_banner()  # 例外が出なければOK
        self.assertIsNone(self.win._update_banner)


class TestOnUpdateCheckFinished(unittest.TestCase):
    def setUp(self):
        self.win = make_window()

    def tearDown(self):
        self.win.close()

    def test_newer_version_in_response_shows_banner(self):
        body = json.dumps({"tag_name": "v9.9.9", "html_url": "https://example.invalid/x"}).encode("utf-8")
        reply = FakeReply(body=body)
        self.win._on_update_check_finished(reply)
        self.assertIsNotNone(self.win._update_banner)
        self.assertTrue(reply.delete_called)

    def test_same_version_in_response_does_not_show_banner(self):
        body = json.dumps({"tag_name": f"v{M.APP_VERSION}"}).encode("utf-8")
        reply = FakeReply(body=body)
        self.win._on_update_check_finished(reply)
        self.assertIsNone(self.win._update_banner)

    def test_network_error_does_not_raise_or_show_banner(self):
        reply = FakeReply(error=QNetworkReply.NetworkError.HostNotFoundError)
        self.win._on_update_check_finished(reply)  # 例外が出なければOK
        self.assertIsNone(self.win._update_banner)
        self.assertTrue(reply.delete_called)

    def test_malformed_json_does_not_raise(self):
        reply = FakeReply(body=b"{not valid json")
        self.win._on_update_check_finished(reply)  # 例外が出なければOK
        self.assertIsNone(self.win._update_banner)
        self.assertTrue(reply.delete_called)


class TestCheckForUpdatesSmoke(unittest.TestCase):
    def test_check_for_updates_does_not_raise(self):
        """
        実際にネットワークリクエストを投げる経路そのものが例外を出さないことだけを
        確認する（応答の中身はテスト環境のネットワーク状況に依存するため検証しない）。
        """
        get_app()
        win = make_window()
        try:
            win._check_for_updates()  # 例外が出なければOK
        finally:
            win.close()


class TestWindowTitle(unittest.TestCase):
    def test_title_includes_app_name_and_version(self):
        win = make_window()
        try:
            title = win.windowTitle()
            self.assertIn("OreHighlighter", title)
            self.assertIn(M.APP_VERSION, title)
            self.assertIn("鉱石視認性向上ツール", title)
        finally:
            win.close()


if __name__ == "__main__":
    unittest.main()
