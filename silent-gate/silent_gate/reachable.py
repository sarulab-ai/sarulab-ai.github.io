"""HTTP 200 を「読者に読める」の根拠にしない。

実際に起きたこと
----------------
読者向けの案内リンクを3箇所に貼った。自分のブラウザでは開けた。
数週間後、CEOがシークレットウィンドウで開いたら「Sign in to view this page」だった。

**cookieなしで取得しても、サーバーは 200 を返した。**
**HTMLには "Sign in" という文字列すら含まれていなかった**(JSで描画されるため)。
ステータスコードもHTMLの文字列検索も、どちらも「読める」と言っていた。

唯一の手掛かりは、**可視テキストが57文字しかなかったこと**だけだった。

このモジュールは、その57文字を見る。
そして **判定できない場合に OK を返さない**。SPAのシェルは、読者に開けるサイト
(Instagram等)と、開けないサイト(ログイン必須のツール)とで、cookieなしの
取得結果が区別できない。区別できないものを「たぶん大丈夫」にしない。
"""
from __future__ import annotations

import html
import re
import urllib.error
import urllib.request
from typing import NamedTuple

UA = "silent-gate/0.1 (reachability check; no cookies sent)"
MIN_VISIBLE = 200  # これ未満は「中身がある」と言い切れない

LOGIN_WALL = re.compile(
    r"(sign in to (view|continue)|log ?in to (view|continue)|"
    r"ログインして(ください|表示)|ログインが必要|会員登録が必要|"
    r"このページを表示するにはログイン)", re.I)

_TAGS = re.compile(r"<(script|style|noscript|template)\b[^>]*>.*?</\1>", re.S | re.I)


class Verdict(NamedTuple):
    status: str      # OK / DEAD / LOGIN_WALL / NO_PUBLIC_CONTENT / UNKNOWN
    detail: str
    http: int = 0
    visible_chars: int = 0

    @property
    def readable(self) -> bool:
        """読者が読めると**言い切れる**ときだけ True。UNKNOWN は False。"""
        return self.status == "OK"


def visible_text(src: str) -> str:
    src = _TAGS.sub(" ", src)
    src = re.sub(r"<[^>]+>", " ", src)
    return re.sub(r"\s+", " ", html.unescape(src)).strip()


def reachable(url: str, timeout: int = 20, min_visible: int = MIN_VISIBLE) -> Verdict:
    """cookieを一切送らずに取得し、読者に中身が見えているかを判定する。"""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            code = r.status
            raw = r.read()
            ctype = (r.headers.get_content_type() or "").lower()
            enc = r.headers.get_content_charset() or "utf-8"
    except urllib.error.HTTPError as e:
        return Verdict("DEAD", f"HTTP {e.code}", e.code)
    except Exception as e:  # noqa: BLE001
        return Verdict("UNKNOWN", f"取得できなかった: {type(e).__name__}: {e}")

    if not ctype.startswith("text/") and "html" not in ctype:
        return Verdict("OK", f"HTMLではない({ctype})", code)

    body = raw.decode(enc, "replace")
    vt = visible_text(body)

    if LOGIN_WALL.search(body) or LOGIN_WALL.search(vt):
        return Verdict("LOGIN_WALL", "ログインを要求する文言がある", code, len(vt))

    if len(vt) < min_visible:
        return Verdict(
            "NO_PUBLIC_CONTENT",
            f"200が返るが可視テキストが{len(vt)}文字しかない。"
            "JSで描画されるページは、読者に開けるものと開けないものが"
            "cookieなしでは区別できない。ブラウザでの実確認が要る",
            code, len(vt))

    return Verdict("OK", f"可視テキスト{len(vt)}文字", code, len(vt))
