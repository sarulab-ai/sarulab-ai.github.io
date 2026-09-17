"""取得失敗を「0件」として扱えなくする。

実際に起きたこと
----------------
Google Driveのトークンが失効したのに、受信処理は例外を握りつぶして
空リストを返し、画面には「新規TASKなし」と表示され続けた。
その裏で、8日間に届いていた27件の指示が1件も処理されなかった。

エラーは1つも出ていない。ログは全部 SUCCESS だった。

原因はコードのこの形である:

    try:
        items = api.list()
    except Exception:
        items = []          # ← ここで「失敗」が「空」に化ける
    if not items:
        print("新規なし")   # ← 嘘ではないが、真実でもない

`Failed` は「空」のふりをしない。len() も for も真偽判定も例外を投げる。
呼び出し側は、失敗を必ず一度は見ることになる。
"""
from __future__ import annotations

from typing import Any, Generic, Iterator, TypeVar, Union

T = TypeVar("T")


class SilentFailure(RuntimeError):
    """取得に失敗した値を、空として扱おうとしたときに投げられる。"""


class Failed(Generic[T]):
    """取得できなかったことを表す。空のコレクションとしては振る舞わない。"""

    __slots__ = ("reason", "cause")

    def __init__(self, reason: str, cause=None) -> None:
        self.reason = reason
        self.cause = cause

    # 「空」として扱われそうな入口を全部塞ぐ
    def _boom(self, how: str) -> None:
        raise SilentFailure(
            f"取得に失敗しています（{self.reason}）。{how}できません。"
            "0件・空・該当なしとして扱わないでください。"
        ) from self.cause

    def __bool__(self) -> bool: self._boom("真偽判定"); return False
    def __len__(self) -> int: self._boom("件数の取得"); return 0
    def __iter__(self) -> Iterator[T]: self._boom("反復"); return iter(())
    def __getitem__(self, i: Any) -> T: self._boom("要素の取得"); raise IndexError
    def __contains__(self, x: Any) -> bool: self._boom("包含判定"); return False

    def __repr__(self) -> str:
        return f"Failed({self.reason!r})"

    # 明示的に扱うための出口
    @property
    def failed(self) -> bool:
        return True

    def unwrap_or(self, default: T) -> T:
        """失敗を承知のうえで既定値を使う。ここを通った事実はコードに残る。"""
        return default


class Fetched(Generic[T]):
    """取得に成功したことを表す。中身が空でも「空だと確認できた」という意味を持つ。"""

    __slots__ = ("value",)

    def __init__(self, value: T) -> None:
        self.value = value

    def __bool__(self) -> bool: return bool(self.value)
    def __len__(self) -> int: return len(self.value)  # type: ignore[arg-type]
    def __iter__(self) -> Iterator[Any]: return iter(self.value)  # type: ignore[call-overload]
    def __getitem__(self, i: Any) -> Any: return self.value[i]  # type: ignore[index]
    def __contains__(self, x: Any) -> bool: return x in self.value  # type: ignore[operator]
    def __repr__(self) -> str: return f"Fetched({self.value!r})"

    @property
    def failed(self) -> bool:
        return False

    def unwrap_or(self, default: T) -> T:
        return self.value


Result = Union[Fetched, Failed]


def attempt(fn, *args, **kwargs) -> Result:
    """例外を Failed に変える。except で空リストに落とすのをやめるための入口。"""
    try:
        return Fetched(fn(*args, **kwargs))
    except Exception as e:  # noqa: BLE001
        return Failed(f"{type(e).__name__}: {e}", e)
