"""silent-gate — AIエージェントに、証明できない成功を言わせないための小さなゲート集。

AIエージェントの本番事故は、例外で落ちない。
「成功しました」と言いながら、何も起きていない。

  failure.py   取得失敗を「0件」として扱えなくする
  reachable.py HTTP 200 を「読者に読める」の根拠にしない
  verdict.py   見ていないものを「確認した」と言わせない
  coverage.py  ゲートが「対象外」を「合格」として返さないようにする
  ledger.py    検出を print だけで終わらせない。気づかれるまで残す

いずれも、実際に起きた事故から作られている。詳細は各モジュールの冒頭と README。
"""
from .failure import Failed, Fetched, SilentFailure, attempt          # noqa: F401
from .reachable import Verdict, reachable, visible_text               # noqa: F401
from .verdict import FAIL, INCOMPLETE, PASS, Item, Report             # noqa: F401
from .coverage import Coverage, Inapplicable, Outcome, guard          # noqa: F401
from .ledger import Ledger                                            # noqa: F401

__version__ = "0.2.0"
