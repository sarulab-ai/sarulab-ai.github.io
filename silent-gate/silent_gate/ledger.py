"""検出を print だけで終わらせない。気づかれるまで残す。

実際に起きたこと
----------------
Slackに届いた新しい投稿を拾う仕組みを作った。動いていた。ちゃんと検出していた。
そして結果を **print していた**。

無人実行から呼ばれると、その print はログファイルへ流れる。誰も読まない。
さらに悪いことに「一度報告したもの」を既読リストへ入れる設計だったので、**二度と出てこない**。

2026-09-17に数えたら、3件が誰にも読まれないまま消えていた。

    09/16 22:58  夜間作業の優先順位指示        … 未読
    09/17 07:36  「今朝までに何を完了したか報告して」 … **8時間放置**
    09/17 15:12  note4本の審査結果            … 人が口頭で教えるまで気づかず

検出は成功していた。通知も成功していた。**受け取る側が居なかっただけ**である。

`Ledger` は、検出を**人が「見た」と書くまで消さない**。
「報告したか」(seen)と「人が反映したか」(acknowledged)は別物で、前者だけを持つと報告は失われる。

使い方
------
    from silent_gate import Ledger

    led = Ledger("~/.myapp/unread.json")
    led.record("slack:1789625525", "チャッピーからの審査結果", source="#jarvis-inbox")

    if led.open_items():           # 未処理があるか
        raise SystemExit(led.summary())   # ← ここで本番作業を止める

    led.acknowledge("slack:1789625525", note="manifestへPASSを反映済み")
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


class Ledger:
    """気づかれるまで消えない検出の置き場。

    print は流れる。ファイルは残る。**残っている限り、呼び出し側は止められる。**
    """

    def __init__(self, path, now=None) -> None:
        self.path = Path(path).expanduser()
        self._now = now or (lambda: datetime.now().astimezone().isoformat(timespec="seconds"))

    # ------------------------------------------------------------------ 内部
    def _load(self) -> Dict[str, dict]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError:
            # 壊れたファイルを「空」として扱わない。壊れていることを知らせる
            raise RuntimeError(f"未処理リストが壊れています: {self.path}。"
                               "空として扱うと未処理が消えるため、中身を確認してください")

    def _save(self, d: Dict[str, dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")

    # ------------------------------------------------------------------ 公開
    def record(self, key: str, what: str, source: str = "", **extra) -> bool:
        """検出を記録する。既にあれば**上書きしない**(最初に気づいた時刻を残す)。戻り値は新規かどうか。"""
        d = self._load()
        if key in d:
            return False
        d[key] = {"what": what, "source": source, "found_at": self._now(), **extra}
        self._save(d)
        return True

    def open_items(self) -> List[dict]:
        """未処理の検出。古い順。"""
        d = self._load()
        items = [{"key": k, **v} for k, v in d.items()]
        return sorted(items, key=lambda x: x.get("found_at", ""))

    def acknowledge(self, key: str, note: str) -> None:
        """人が見て、**どこへ反映したか**を書いて初めて消える。

        `note` を空にできないのは、「見た」だけで消せると、見ただけで消えるからである。
        """
        if not note:
            raise ValueError("どこへ反映したかを書いてください(空では消せません)")
        d = self._load()
        if key not in d:
            raise KeyError(f"未処理リストに {key} がありません")
        del d[key]
        self._save(d)

    def summary(self) -> str:
        items = self.open_items()
        if not items:
            return "未処理の検出はありません"
        head = f"**未処理の検出が {len(items)} 件あります。**"
        for i in items:
            head += f"\n  - [{i.get('found_at','')}] {i.get('what','')}"
            if i.get("source"):
                head += f"  ({i['source']})"
            head += f"\n      key={i['key']}"
        head += "\n  → 中身を読み、反映先を書いて acknowledge(key, note=...) してください"
        return head

    def __len__(self) -> int: return len(self.open_items())
    def __bool__(self) -> bool: return bool(self.open_items())
    def __str__(self) -> str: return self.summary()
