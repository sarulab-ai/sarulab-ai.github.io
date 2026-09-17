"""実際に起きた事故を再現し、ゲートが止めることを確認する。

テストの名前は、事故の名前である。
"""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from silent_gate import (Failed, Fetched, SilentFailure, attempt,
                         Report, PASS, FAIL, INCOMPLETE, visible_text)
from silent_gate.reachable import LOGIN_WALL, MIN_VISIBLE


class トークン失効を新規なしと表示した件(unittest.TestCase):
    """Driveトークンが切れたのに『新規TASKなし』と出し続け、指示27件を8日間取りこぼした。"""

    def test_失敗は空として扱えない(self):
        r = attempt(lambda: (_ for _ in ()).throw(RuntimeError("invalid_grant")))
        self.assertTrue(r.failed)
        for op, fn in [("真偽判定", lambda: bool(r)), ("len", lambda: len(r)),
                       ("for", lambda: [x for x in r]), ("in", lambda: 1 in r),
                       ("[0]", lambda: r[0])]:
            with self.subTest(op=op), self.assertRaises(SilentFailure):
                fn()

    def test_事故のコードそのものが通らなくなる(self):
        """`if not items: print('新規なし')` が例外になることを示す。"""
        items = attempt(lambda: (_ for _ in ()).throw(ConnectionError("token expired")))
        with self.assertRaises(SilentFailure):
            if not items:            # ← 事故当時ここが True になっていた
                pass

    def test_本当に0件のときは通る(self):
        items = attempt(lambda: [])
        self.assertFalse(items.failed)
        self.assertEqual(len(items), 0)
        self.assertFalse(bool(items))       # 空は空として扱ってよい

    def test_失敗を承知で既定値を使う出口は残す(self):
        r = Failed("timeout")
        self.assertEqual(r.unwrap_or(["既定"]), ["既定"])

    def test_理由が失われない(self):
        r = attempt(lambda: 1 / 0)
        self.assertIn("ZeroDivisionError", r.reason)
        with self.assertRaises(SilentFailure) as cm:
            len(r)
        self.assertIn("0件", str(cm.exception))


class 二百が返るのに読者には何も見えていなかった件(unittest.TestCase):
    """cookieなしで200・HTMLに"Sign in"すら無し。可視テキスト57文字だけが手掛かりだった。"""

    def test_JSシェルは可視テキストで見抜ける(self):
        shell = ('<html><head><title>App</title>'
                 '<script>var x="Sign in to view this page";</script></head>'
                 '<body><div id="root"></div></body></html>')
        self.assertLess(len(visible_text(shell)), MIN_VISIBLE)

    def test_scriptの中身を可視テキストに数えない(self):
        """script内の長い文字列で嵩増しされると、シェルを中身ありと誤認する。"""
        padded = '<html><body><script>' + 'x' * 5000 + '</script><div></div></body></html>'
        self.assertLess(len(visible_text(padded)), MIN_VISIBLE)

    def test_ログイン要求の文言は拾う(self):
        for s in ["Sign in to view this page", "ログインが必要です",
                  "このページを表示するにはログインしてください", "Log in to continue"]:
            with self.subTest(s=s):
                self.assertTrue(LOGIN_WALL.search(s))

    def test_普通の記事は誤検出しない(self):
        s = "ログイン不要でお読みいただけます。" + "本文" * 200
        self.assertIsNone(LOGIN_WALL.search(s))


class 見ていない動画を検品したと報告した件(unittest.TestCase):
    """フレーム検査は全項目クリア。しかし誰も動画を通しで見ていなかった。"""

    def test_全項目クリアでも未確認が残ればPASSにならない(self):
        r = (Report("完成動画")
             .ok("カメラ固定").ok("キャラクター残存").ok("足元の影").ok("偽文字なし")
             .unverifiable("通しで視聴", "この環境では動画をデコードできない"))
        self.assertEqual(r.verdict(), INCOMPLETE)
        self.assertNotEqual(r.verdict(), PASS)
        self.assertEqual(r.exit_code(), 3)
        self.assertIn("確認できていません", r.summary())

    def test_未確認が無ければPASS(self):
        r = Report("原稿").ok("誤字").ok("数値の裏取り")
        self.assertEqual(r.verdict(), PASS)
        self.assertEqual(r.exit_code(), 0)

    def test_NGが最優先(self):
        r = Report().ok("a").unverifiable("b", "見られない").ng("c", "壊れている")
        self.assertEqual(r.verdict(), FAIL)
        self.assertEqual(r.exit_code(), 1)

    def test_理由を書かない未確認は認めない(self):
        with self.assertRaises(ValueError):
            Report().unverifiable("通しで視聴", "")

    def test_未確認の項目名が結論に出る(self):
        s = Report("動画").ok("a").unverifiable("音ズレ", "音声を再生できない").summary()
        self.assertIn("音ズレ", s)
        self.assertIn("音声を再生できない", s)


if __name__ == "__main__":
    unittest.main(verbosity=2)
