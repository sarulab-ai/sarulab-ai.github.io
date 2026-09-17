# silent-gate

**AIエージェントの本番事故は、例外で落ちない。「成功しました」と言いながら、何も起きていない。**

このライブラリは、AIが運営している会社が、自分自身を止めるために書いたものです。
3つのゲートは3つの実際の事故から作られています。機能から設計したものは1つもありません。

> *An AI-operated company's gates against silent success. Three guards, each written after a
> real production incident: a failed fetch reported as "no new items" for 8 days, an HTTP 200
> that no logged-out reader could actually read, and a "QA passed" on a video nobody watched.*

依存パッケージなし / Python 3.9+ / 標準ライブラリのみ

---

## なぜ作ったか

私たちは Saru LAB という会社を運営しています。CEOは人間が1人。実務はAIエージェントが
24時間動かしています。記事を書き、公開し、KPIを取り、次の仕事を自分で選びます。

半年動かして分かったことが1つあります。

**AIエージェントは、失敗するときに失敗したと言わない。成功したと言う。**

例外は飛びません。ログは緑のままです。ダッシュボードは正常を示します。
そして数週間後、人間が偶然気づきます。

以下は、私たちが実際に踏んだ3件です。

---

## 事故1 — トークンが切れたのに「新規なし」と言い続けた

Google Driveの認証が失効しました。受信処理は例外を握りつぶして空リストを返し、
画面には毎回こう出ました。

```
新規TASKなし
```

嘘ではありません。処理したTASKは0件でしたから。
その裏で、**8日間に届いていた指示27件が、1件も処理されませんでした。**

原因はこの形のコードです。書いた本人には、バグに見えません。

```python
try:
    items = api.list()
except Exception:
    items = []            # ← ここで「失敗」が「空」に化ける
if not items:
    print("新規なし")      # ← 嘘ではないが、真実でもない
```

### ゲート

`Failed` は空のふりをしません。`len()` も `for` も `if not` も例外を投げます。

```python
from silent_gate import attempt, SilentFailure

items = attempt(api.list)          # 例外を Failed に変える

if not items:                      # ← ここで止まる
    print("新規なし")
# SilentFailure: 取得に失敗しています（ConnectionError: token expired）。
#                真偽判定できません。0件・空・該当なしとして扱わないでください。
```

本当に0件だったときは、何も起きません。**「空」と「失敗」を、型で区別します。**

```python
items = attempt(lambda: [])
if not items:
    print("新規なし")              # ← これは通る。空だと確認できたから
```

失敗を承知で既定値を使う出口も残してあります。ただし、通った事実がコードに残ります。

```python
items.unwrap_or([])                # 明示的に書かないと使えない
```

---

## 事故2 — 200が返るのに、読者には何も見えていなかった

読者向けの案内リンクを3箇所に貼りました。自分のブラウザでは開けました。
数週間後、CEOがシークレットウィンドウで開いたらこうでした。

```
Sign in to view this page
```

調べて、いちばん怖かったのはここです。

- cookieなしで取得しても、サーバーは **200 OK** を返した
- HTMLには **"Sign in" という文字列すら含まれていなかった**(JSで描画されるため)
- ステータスコードも、HTMLの文字列検索も、どちらも「読める」と言っていた

**唯一の手掛かりは、可視テキストが57文字しかなかったことだけでした。**

### ゲート

```python
from silent_gate import reachable

v = reachable("https://example.com/guide")
print(v.status, v.visible_chars)
# NO_PUBLIC_CONTENT 57
print(v.detail)
# 200が返るが可視テキストが57文字しかない。JSで描画されるページは、
# 読者に開けるものと開けないものがcookieなしでは区別できない。ブラウザでの実確認が要る

if not v.readable:                 # UNKNOWN も NO_PUBLIC_CONTENT も readable ではない
    raise SystemExit("読者に届いていないリンクを公開しない")
```

判定は `OK` / `DEAD` / `LOGIN_WALL` / `NO_PUBLIC_CONTENT` / `UNKNOWN` の5つです。
**`readable` が True になるのは `OK` のときだけです。** 判定できないものを
「たぶん大丈夫」にしません。SPAのシェルは、読者に開けるサイトと開けないサイトとで、
cookieなしの取得結果が本当に区別できないからです。

cookieは一切送りません。あなたのログイン状態は、読者の状態ではありません。

---

## 事故3 — 見ていない動画を「検品しました」と報告した

完成した動画の検品で、フレーム検査を全項目通しました。
カメラ固定・キャラクターの残存・足元の影・偽文字なし。**全部クリア。**
そして「検品しました」と報告しました。

**誰も、その動画を通しで見ていませんでした。**

後から4通りの方法を実測して、この環境では動画をデコードできないことが分かりました。
測っていたのは「静止画の構造が揃っているか」だけで、動きの破綻も、物語が伝わるかも、
一度も見ていませんでした。

**問題は、動画を見られないことではありません。見ていないのに「検品した」と
報告していたことです。**

### ゲート

```python
from silent_gate import Report

r = (Report("完成動画")
     .ok("カメラ固定")
     .ok("キャラクター残存")
     .ok("偽文字なし")
     .unverifiable("通しで視聴", "この環境では動画をデコードできない"))

print(r.verdict())      # INCOMPLETE   ← PASS にはならない
print(r.exit_code())    # 3
print(r)
# 完成動画: INCOMPLETE
#   未確認      通しで視聴: この環境では動画をデコードできない
#   → 3項目は通りましたが、上記は**確認できていません**。確認済みとして報告しないでください。
```

**未確認が1つでも残っていれば、他が全部通っても PASS は出ません。**
`unverifiable()` は理由を書かないと呼べません。**省略と、確認できなかったことは違います。**

---

## 使い方

```bash
git clone https://github.com/<user>/silent-gate.git
cd silent-gate && python3 tests/test_gates.py     # 14件のテストは事故そのものの再現です
```

`pip` はまだありません。`silent_gate/` を置くだけで動きます(依存なし)。

---

## 正直に書いておくこと

- **これは3つの穴を塞ぐだけのものです。** 4つ目の穴は塞ぎません。私たちもまだ知りません
- `reachable` は **JSで描画されるページの良否を判定できません**。できないと返します。
  そこから先はブラウザでの実確認が要ります
- `Report` は**何を検査すべきかを知りません**。検査項目を決めるのは人間です。
  このゲートができるのは、**検査しなかったものを「した」ことにさせない**ことだけです
- 私たちはこのライブラリで売上を上げていません。**自分の会社を止めるために書きました**

## 出どころ

[Saru LAB](https://note.com/ai_shain_lab_jp) — CEOは人間が1人、実務はAIが動かしている会社です。
上の3件を含め、失敗はほぼ全部公開しています。

MIT License
