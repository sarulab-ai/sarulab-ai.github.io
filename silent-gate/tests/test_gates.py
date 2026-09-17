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




class 連載順序ゲートが四本とも対象外になっていた件(unittest.TestCase):
    """ID文字列から話数を読む実装で、命名規則の違う連載4本が全部素通りしていた。

    返ってきていたのは OK。合格と見分けがつかなかった。
    """

    def setUp(self):
        from silent_gate import guard, Inapplicable

        @guard("連載順序")
        def gate(entry):
            # 当時の実装: IDから "EP<N>" を読む。読めなければ「連載ではない」
            import re
            m = re.search(r"EP(\d+)$", entry["id"])
            if not m:
                raise Inapplicable("IDから話数を読めない")
            return entry.get("prev_published", False), "前話が未公開" if not entry.get("prev_published") else ""
        self.gate = gate

    def test_話数が読めない対象は合格にならない(self):
        o = self.gate({"id": "FREE-ai-tool-jiko5-v1"})
        self.assertFalse(o.passed)          # ← 当時はここが True 相当だった
        self.assertTrue(o.blocked)
        self.assertEqual(o.state, "inapplicable")
        self.assertIn("適用できず", str(o))

    def test_普通に判定できるものは今までどおり(self):
        self.assertTrue(self.gate({"id": "SERIES-EP02", "prev_published": True}).passed)
        self.assertFalse(self.gate({"id": "SERIES-EP02", "prev_published": False}).passed)

    def test_一件も適用できていないゲートは信用できないと分かる(self):
        from silent_gate import Coverage
        cov = Coverage(self.gate, [{"id": "FREE-a-v1"}, {"id": "FREE-b-v1"},
                                   {"id": "FREE-c-v1"}, {"id": "FREE-d-v1"}])
        self.assertEqual(cov.applied, 0)
        self.assertEqual(len(cov.failed), 0)      # 不合格0件。健全に見える
        self.assertFalse(cov.trustworthy)         # しかし信用できない
        self.assertIn("なにも守っていません", cov.summary())

    def test_一部だけ適用できている場合も数が出る(self):
        from silent_gate import Coverage
        cov = Coverage(self.gate, [{"id": "S-EP01", "prev_published": True},
                                   {"id": "FREE-x-v1"}])
        self.assertEqual(cov.applied, 1)
        self.assertEqual(len(cov.inapplicable), 1)
        self.assertTrue(cov.trustworthy)
        self.assertIn("合格として数えないでください", cov.summary())


class 検出をプリントだけで終わらせて八時間放置した件(unittest.TestCase):
    """Slackの新規投稿を検出していたが print するだけで、ログに流れて誰も読まなかった。"""

    def setUp(self):
        import tempfile
        from silent_gate import Ledger
        self.tmp = tempfile.TemporaryDirectory()
        self.led = Ledger(Path(self.tmp.name) / "unread.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_気づくまで消えない(self):
        self.led.record("slack:1789597737", "今朝までに何を完了したか報告して", source="#jarvis-inbox")
        self.assertTrue(self.led)                     # 未処理あり → 呼び出し側を止められる
        self.assertEqual(len(self.led), 1)
        self.assertIn("報告して", self.led.summary())

    def test_反映先を書かないと消せない(self):
        self.led.record("k", "審査結果")
        with self.assertRaises(ValueError):
            self.led.acknowledge("k", note="")
        self.assertEqual(len(self.led), 1)            # 残ったまま

    def test_反映先を書けば消える(self):
        self.led.record("k", "審査結果")
        self.led.acknowledge("k", note="manifestへPASSを反映")
        self.assertEqual(len(self.led), 0)
        self.assertFalse(self.led)

    def test_同じ検出を二度記録しても最初の時刻が残る(self):
        self.assertTrue(self.led.record("k", "1回目"))
        self.assertFalse(self.led.record("k", "2回目"))
        self.assertEqual(self.led.open_items()[0]["what"], "1回目")

    def test_壊れたファイルを空として扱わない(self):
        self.led.path.parent.mkdir(parents=True, exist_ok=True)
        self.led.path.write_text("{壊れている", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            self.led.open_items()




class コードから静かに失敗する形を探す(unittest.TestCase):
    """既に書かれたコードの中から、同じ形を見つけられるか。"""

    def _scan(self, code: str):
        import tempfile, os
        from silent_gate import scan as S
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "x.py"
            f.write_text(code, encoding="utf-8")
            return {x.rule for x in S.scan(Path(d))}

    def test_S1_失敗を空にする形を見つける(self):
        self.assertIn("S1", self._scan(
            "def f():\n    try:\n        return api()\n    except Exception:\n        return []\n"))

    def test_S1_代入版も見つける(self):
        self.assertIn("S1", self._scan(
            "def f():\n    try:\n        items = api()\n    except Exception:\n        items = []\n    return items\n"))

    def test_S2_二百だけで成功にする形を見つける(self):
        self.assertIn("S2", self._scan(
            "def f(r):\n    if r.status_code == 200:\n        return True\n    return False\n"))

    def test_S5_握りつぶしを見つける(self):
        self.assertIn("S5", self._scan("def f():\n    try:\n        g()\n    except ValueError:\n        pass\n"))

    def test_正しく書かれたコードは指摘しない(self):
        rules = self._scan(
            "def f():\n"
            "    try:\n"
            "        return Fetched(api())\n"
            "    except Exception as e:\n"
            "        return Failed(str(e))\n")
        self.assertEqual(rules, set())

    def test_例外の理由を残していればS1にしない(self):
        rules = self._scan(
            "def f():\n    try:\n        return api()\n    except Exception as e:\n        raise RuntimeError(e)\n")
        self.assertNotIn("S1", rules)

    def test_構文エラーのファイルで落ちない(self):
        import tempfile
        from silent_gate import scan as S
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "broken.py").write_text("def (", encoding="utf-8")
            self.assertEqual(S.scan(Path(d)), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
