"""ゲートが「対象外」を「合格」として返さないようにする。

実際に起きたこと
----------------
連載の公開順序ゲートを書いた。第N話を出す前に第N-1話が公開済みかを確かめる門である。
2026-09-05に実際の事故(第1〜23話が未公開のまま第24話が先に公開された)を受けて作り、
以後ずっと緑を返し続けていた。

2026-09-17、別の連載を追加したときに気づいた。
そのゲートは **ID文字列から話数を読む実装**だった。

    AISHAIN-JINJI-HYOKA-EP18   → シリーズ=AISHAIN-JINJI-HYOKA, 話数=18  ✅
    FREE-ai-tool-jiko5-v1      → 話数が読めない → 「連載ではない」→ **OK**

新しい連載4本は命名規則が違った。**4本とも順序ゲートの対象外になっていた。**
第3話が先に承認されれば、第1話より先に公開できる状態だった。守っているつもりの門が、
守るべきものを1本も守っていなかった。

**そして、返ってきていたのは `OK` である。** 合格と見分けがつかない。

ここで言いたいのは「バグがあった」ではない。
**対象外を合格として返すゲートは、ゲートが無いより悪い。**
無ければ「検査していない」と分かるが、あると「検査して問題なかった」と誤解される。

使い方
------
    from silent_gate import guard, Inapplicable

    @guard("連載順序")
    def series_order(entry):
        n = parse_episode(entry["id"])
        if n is None:
            raise Inapplicable("IDから話数を読めない")   # ← OKにならない
        return previous_published(entry, n)

    r = series_order(entry)
    r.passed        # 合格と言い切れるときだけ True
    r.state         # "pass" / "fail" / "inapplicable"

`Coverage` を使うと、**集団に対してゲートが何件に当たったか**を出せる。
「0件不合格」と「0件しか当たっていない」を区別するためのものである。
"""
from __future__ import annotations

import functools
from typing import Any, Callable, List, NamedTuple

PASS = "pass"
FAIL = "fail"
INAPPLICABLE = "inapplicable"


class Inapplicable(Exception):
    """このゲートは、この対象には当てられなかった。合格ではない。"""


class Outcome(NamedTuple):
    gate: str
    state: str
    detail: str = ""
    subject: Any = None

    @property
    def passed(self) -> bool:
        """**合格と言い切れるときだけ True。** 対象外は False。"""
        return self.state == PASS

    @property
    def blocked(self) -> bool:
        """止めるべきときに True。不合格はもちろん、**当てられなかった場合も止める**。"""
        return self.state != PASS

    def __str__(self) -> str:
        label = {PASS: "合格", FAIL: "不合格", INAPPLICABLE: "**適用できず**"}[self.state]
        return f"[{self.gate}] {label}" + (f": {self.detail}" if self.detail else "")


def guard(name: str) -> Callable:
    """検査関数を Outcome を返すゲートにする。

    - True を返した → 合格
    - False を返した → 不合格
    - `Inapplicable` を投げた → **適用できず**(合格にはならない)
    - `(bool, detail)` を返してもよい
    """
    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(subject: Any = None, *a, **kw) -> Outcome:
            try:
                r = fn(subject, *a, **kw) if subject is not None or a or kw else fn()
            except Inapplicable as e:
                return Outcome(name, INAPPLICABLE, str(e) or "理由未記載", subject)
            detail = ""
            if isinstance(r, tuple) and len(r) == 2:
                r, detail = r
            return Outcome(name, PASS if r else FAIL, detail, subject)
        wrapper.gate_name = name  # type: ignore[attr-defined]
        return wrapper
    return deco


class Coverage:
    """ゲートを集団に当てて、**何件に当たったか**まで報告する。

    「不合格0件」だけを見ると、1件も当たっていないゲートが健全に見える。
    """

    def __init__(self, gate: Callable, subjects) -> None:
        self.gate = gate
        self.outcomes: List[Outcome] = [gate(s) for s in subjects]

    @property
    def total(self) -> int: return len(self.outcomes)
    @property
    def passed(self) -> List[Outcome]: return [o for o in self.outcomes if o.state == PASS]
    @property
    def failed(self) -> List[Outcome]: return [o for o in self.outcomes if o.state == FAIL]
    @property
    def inapplicable(self) -> List[Outcome]: return [o for o in self.outcomes if o.state == INAPPLICABLE]

    @property
    def applied(self) -> int:
        """実際に判定できた件数。これが0なら、そのゲートは何も守っていない。"""
        return len(self.passed) + len(self.failed)

    @property
    def trustworthy(self) -> bool:
        """**当たった件数が0なら、不合格0件を根拠にしてはいけない。**"""
        return self.total == 0 or self.applied > 0

    def summary(self) -> str:
        name = getattr(self.gate, "gate_name", "(無名)")
        head = (f"[{name}] {self.total}件中 {self.applied}件に適用 "
                f"(合格{len(self.passed)} 不合格{len(self.failed)} 適用できず{len(self.inapplicable)})")
        if not self.trustworthy:
            head += "\n  ⚠ **1件も適用できていません。** このゲートは現在なにも守っていません"
        elif self.inapplicable:
            head += f"\n  ⚠ {len(self.inapplicable)}件に適用できていません。合格として数えないでください"
            for o in self.inapplicable[:5]:
                head += f"\n     - {o.subject}: {o.detail}"
        return head

    def __str__(self) -> str: return self.summary()
