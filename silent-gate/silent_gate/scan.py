"""コードの中から「静かに失敗する形」を探す。

なぜ静的検査なのか
------------------
このライブラリの3つのゲートは、**これから書くコード**を守る。
しかし世の中のコードは既に書かれている。しかも事故の形は、書いた本人には
バグに見えない(`except: items = []` は「落ちないようにした丁寧なコード」に見える)。

だから、**既にあるコードから同じ形を探す**道具を足した。

    python3 -m silent_gate.scan yourrepo/

見つけられるもの / 見つけられないもの
--------------------------------------
機械で確実に分かるのは「形」だけである。**意図までは分からない。**
だからこの道具は「直せ」とは言わない。「**ここは静かに失敗しうる**」と場所を出すだけで、
判断は人に残す(これ自体がverdict.pyの思想と同じ)。

見つけられる:
  S1 例外を握って空にする      except: ... = [] / return [] / return None
  S2 200を成功の根拠にする      status_code == 200 / resp.ok だけで進む
  S3 検出をprintで終わらせる    見つけた分岐でprintのみ、保存も送信もしない
  S4 判定不能を合格にする        parse失敗・None時に True / OK を返す
  S5 握りつぶし                  except ...: pass (本体がpassだけ)

見つけられない:
  - 意図的にそうしている箇所(正しい場合もある)
  - 動的に組み立てられる処理
  - 「検査すべきものを検査していない」こと自体(コードに現れない)

終了コードは常に0(検査であって門ではない)。件数は標準出力に出す。
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path
from typing import List, NamedTuple

SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "__pycache__", "site-packages",
             "dist", "build", ".mypy_cache", ".pytest_cache"}


class Finding(NamedTuple):
    rule: str
    file: str
    line: int
    detail: str
    snippet: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line}  [{self.rule}] {self.detail}\n      {self.snippet}"


RULES = {
    "S1": "例外を握って「空」にしている。失敗と0件が同じ値になる",
    "S2": "200(またはok)だけを成功の根拠にしている。中身を見ていない",
    "S3": "見つけたのに print だけ。無人実行ではログに流れて誰も読まない",
    "S4": "解釈できなかったときに合格(True/OK)を返している。対象外が合格になる",
    "S5": "例外を pass で握りつぶしている。何が起きたか誰も知らない",
}

_EMPTYISH = (ast.List, ast.Dict, ast.Set, ast.Tuple)


def _is_emptyish(node) -> bool:
    if isinstance(node, ast.Constant) and node.value in (None, 0, False, ""):
        return True
    if isinstance(node, _EMPTYISH) and not getattr(node, "elts", getattr(node, "keys", [1])):
        return True
    return False


def _src(lines: List[str], node) -> str:
    i = getattr(node, "lineno", 1) - 1
    return lines[i].strip()[:110] if 0 <= i < len(lines) else ""


class Visitor(ast.NodeVisitor):
    def __init__(self, path: str, lines: List[str]) -> None:
        self.path, self.lines, self.found = path, lines, []  # type: ignore[var-annotated]

    def add(self, rule: str, node) -> None:
        self.found.append(Finding(rule, self.path, getattr(node, "lineno", 0),
                                  RULES[rule], _src(self.lines, node)))

    # -------------------------------------------------- S1 / S5
    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        body = node.body
        if len(body) == 1 and isinstance(body[0], ast.Pass):
            self.add("S5", node)
        for st in body:
            if isinstance(st, ast.Assign) and _is_emptyish(st.value):
                self.add("S1", st)
            elif isinstance(st, ast.Return) and (st.value is None or _is_emptyish(st.value)):
                self.add("S1", st)
        self.generic_visit(node)

    # -------------------------------------------------- S2
    def visit_Compare(self, node: ast.Compare) -> None:
        try:
            left = ast.unparse(node.left)
        except Exception:  # noqa: BLE001
            left = ""
        if ("status" in left.lower() or "code" in left.lower()) and node.comparators:
            c = node.comparators[0]
            if isinstance(c, ast.Constant) and c.value == 200:
                self.add("S2", node)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr == "ok":
            self.add("S2", node)
        self.generic_visit(node)

    # -------------------------------------------------- S3 / S4
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._func(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node) -> None:  # type: ignore[override]
        self._func(node)
        self.generic_visit(node)

    def _func(self, node) -> None:
        name = node.name.lower()
        detectish = any(k in name for k in ("detect", "scan", "check", "find", "watch", "poll", "collect"))
        if detectish:
            prints, persists = [], False
            for n in ast.walk(node):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "print":
                    prints.append(n)
                if isinstance(n, ast.Call):
                    try:
                        f = ast.unparse(n.func)
                    except Exception:  # noqa: BLE001
                        f = ""
                    if any(k in f for k in ("write_text", "dump", "save", "insert", "post",
                                            "append", "commit", "notify", "send", "record")):
                        persists = True
            if prints and not persists:
                self.add("S3", prints[0])
        # S4: parse系の失敗時に True を返していないか
        for n in ast.walk(node):
            if isinstance(n, ast.If):
                for st in n.body:
                    if isinstance(st, ast.Return) and isinstance(st.value, ast.Constant) \
                            and st.value.value is True:
                        try:
                            cond = ast.unparse(n.test)
                        except Exception:  # noqa: BLE001
                            cond = ""
                        if any(k in cond for k in ("is None", "not ", "== None", "empty", "len(")):
                            self.add("S4", st)


def scan_file(p: Path, root: Path) -> List[Finding]:
    try:
        text = p.read_text(encoding="utf-8")
        tree = ast.parse(text)
    except Exception:  # noqa: BLE001
        return []
    v = Visitor(str(p.relative_to(root)), text.splitlines())
    v.visit(tree)
    return v.found


def scan(root: Path) -> List[Finding]:
    out: List[Finding] = []
    for p in sorted(root.rglob("*.py")):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        out += scan_file(p, root)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="コードから「静かに失敗する形」を探す")
    ap.add_argument("path", nargs="?", default=".")
    ap.add_argument("--rule", choices=sorted(RULES), help="1つのルールだけ表示")
    ap.add_argument("--limit", type=int, default=40)
    a = ap.parse_args(argv)
    root = Path(a.path).resolve()
    found = scan(root)
    if a.rule:
        found = [f for f in found if f.rule == a.rule]
    by: dict = {}
    for f in found:
        by.setdefault(f.rule, []).append(f)
    print(f"■ {root} を検査しました\n")
    for r in sorted(RULES):
        n = len(by.get(r, []))
        print(f"  {r}  {n:4}件  {RULES[r]}")
    print(f"\n  合計 {len(found)}件\n")
    for f in found[: a.limit]:
        print(f)
    if len(found) > a.limit:
        print(f"\n  … 他 {len(found)-a.limit}件(--limit で増やせます)")
    print("\n※ これは「形」の検査です。**意図までは分かりません。**"
          "\n   直すべきかどうかは、各箇所を読んで人が決めてください。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
