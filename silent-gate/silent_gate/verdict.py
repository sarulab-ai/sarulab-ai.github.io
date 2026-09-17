"""見ていないものを「確認した」と言わせない。

実際に起きたこと
----------------
完成した動画の検品で、フレーム検査を全項目通した。
カメラ固定・キャラクターの残存・足元の影・偽文字なし——全部クリア。
そして「検品しました」と報告した。

**誰も、その動画を通しで見ていなかった。** この環境では動画をデコードできない
(4通りの方法を実測して全滅した)ことが後から分かった。
測っていたのは「静止画の構造が揃っているか」だけで、
動きの破綻も、物語が伝わるかも、一度も見ていなかった。

問題は、動画を見られないことではない。
**見ていないのに「検品した」と報告していたこと**である。

`Report` は、検証できなかった項目が1つでも残っていると PASS を出せない。
全項目クリアでも、出るのは `CHECKS_PASSED / UNVERIFIED(...)` である。
"""
from __future__ import annotations

from typing import List, NamedTuple

PASS = "PASS"
FAIL = "FAIL"
INCOMPLETE = "INCOMPLETE"   # 個別検査は通ったが、確認できていない項目が残っている


class Item(NamedTuple):
    name: str
    state: str          # ok / ng / unverifiable
    note: str = ""


class Report:
    """検査結果をためて、正直な結論だけを出す。

    - 1つでも ng があれば FAIL
    - ng が無くても unverifiable が残っていれば INCOMPLETE（PASSにはならない）
    - すべて ok のときだけ PASS
    """

    def __init__(self, subject: str = "") -> None:
        self.subject = subject
        self.items: List[Item] = []

    def ok(self, name: str, note: str = "") -> "Report":
        self.items.append(Item(name, "ok", note)); return self

    def ng(self, name: str, note: str = "") -> "Report":
        self.items.append(Item(name, "ng", note)); return self

    def unverifiable(self, name: str, why: str) -> "Report":
        """確認しようとしたが、確認できなかった。**省略とは違う。**"""
        if not why:
            raise ValueError("なぜ確認できなかったかを必ず書いてください")
        self.items.append(Item(name, "unverifiable", why)); return self

    @property
    def failed(self) -> List[Item]:
        return [i for i in self.items if i.state == "ng"]

    @property
    def unverified(self) -> List[Item]:
        return [i for i in self.items if i.state == "unverifiable"]

    def verdict(self) -> str:
        if self.failed:
            return FAIL
        if self.unverified:
            return INCOMPLETE
        return PASS

    def exit_code(self) -> int:
        return {PASS: 0, FAIL: 1, INCOMPLETE: 3}[self.verdict()]

    def summary(self) -> str:
        v = self.verdict()
        head = f"{self.subject}: {v}" if self.subject else v
        if v == PASS:
            return f"{head}（{len(self.items)}項目すべて確認済み）"
        lines = [head]
        for i in self.failed:
            lines.append(f"  NG          {i.name}: {i.note}")
        for i in self.unverified:
            lines.append(f"  未確認      {i.name}: {i.note}")
        if v == INCOMPLETE:
            n = len([i for i in self.items if i.state == "ok"])
            lines.append(f"  → {n}項目は通りましたが、上記は**確認できていません**。"
                         "確認済みとして報告しないでください。")
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.summary()
