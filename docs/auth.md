# 認証トークン取得手順

AI Company が Claude API を呼び出すために必要な認証情報の取得方法をまとめます。

## 重要：このシステムは「API キー」が必要です

各エージェント（`agents/base_agent.py`）は Anthropic の **Messages API（`/v1/messages`）を直接呼び出します**。
そのため、利用できる認証方法は実質 **`ANTHROPIC_API_KEY`（API キー）のみ**です。

**Claude Pro / Max などのサブスクリプションの OAuth トークン（`claude setup-token` で取得するもの）は
Messages API では使えません。** Anthropic の API はサブスクリプション由来の OAuth トークンを
`OAuth authentication is currently not supported.` というエラーで拒否します
（この対応要望は [GitHub issue #37205](https://github.com/anthropics/claude-code/issues/37205) で
「実装しない（not planned）」として却下されています）。

> サブスクリプション枠でこのシステムを動かしたい場合は、API を直接呼ぶのをやめて
> `claude` CLI（ヘッドレスモード）経由に書き換える必要があります（本リポジトリでは未対応）。
> 詳細は本ドキュメント末尾の「補足」を参照。

```bash
cp .env.example .env
```

---

## API キー（`ANTHROPIC_API_KEY`）— 推奨かつ実質唯一の方法

Anthropic のプラットフォームから発行するキーです。課金はトークン使用量に応じた従量制で、
**サブスクリプションとは別の API クレジット**が必要です。

### 取得手順

1. [Anthropic Console](https://console.anthropic.com)（platform.claude.com）にアクセスしてサインインする
2. **API クレジットを購入する**（残高 0 だと 429 エラーになります）
   - Settings → Billing から $5 程度を購入すれば動作確認には十分です
3. 左メニューの **API Keys** を開く
4. **+ Create Key** をクリックして新しいキーを作成する
5. 表示されたキー（`sk-ant-...`）をコピーする（再表示されないため必ずこの時点で保存）

### `.env` への設定

```env
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxx
```

### 注意事項

- キーは作成直後にしか表示されません。紛失した場合は再発行が必要です
- キーに使用量制限（Spending Limit）を設定することを推奨します（Console → Settings → Limits）
- キーを Git にコミットしないでください（`.env` は `.gitignore` に含まれています）
- **動作確認時はモデルを `claude-haiku-4-5` にすると低コストです**（`.env` の `MODEL`）

---

## 使えない方法（参考）

以下は `base_agent.py` のコード上は受け付けますが、**Messages API 側で拒否されるため
このシステムでは動作しません**。混乱を避けるため記載します。

| 環境変数 | 中身 | このシステムで動くか |
|---|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | `claude setup-token` で取得するサブスク OAuth トークン（`sk-ant-oat01-...`） | ❌ Messages API が拒否 |
| `ANTHROPIC_AUTH_TOKEN` | `Authorization: Bearer` で送るトークン（LLM ゲートウェイ／プロキシ用） | △ サブスク OAuth を入れても拒否される。自前プロキシ経由のとき専用 |

これらのトークンは `claude` CLI 本体や claude.ai では有効ですが、自作コードからの
API 直接呼び出しには使えません。

---

## 優先順位

複数の環境変数が設定されている場合、`base_agent.py` は以下の順で認証情報を使用します。

```
ANTHROPIC_API_KEY  >  ANTHROPIC_AUTH_TOKEN  >  CLAUDE_CODE_OAUTH_TOKEN
```

実際に成功するのは `ANTHROPIC_API_KEY` のみです。

---

## トラブルシュート

**`No auth configured` エラーが出る**

`.env` に認証情報が設定されていないか、変数名が間違っています。`logs/ceo.log` などを確認してください。

```bash
cat logs/ceo.log | grep -i auth
```

**429 Too Many Requests が出る**

- **最も多い原因は API クレジットの残高 0** です。Console（platform.claude.com）で
  クレジットを購入してください
- 残高があるのに出る場合はレート制限（TPM/RPM）超過です。`MODEL=claude-haiku-4-5` に
  変更するか、しばらく待ってから再実行してください

**`OAuth authentication is currently not supported.` が出る**

- `CLAUDE_CODE_OAUTH_TOKEN` または `ANTHROPIC_AUTH_TOKEN` にサブスクリプションの OAuth トークンを
  設定しています。`ANTHROPIC_API_KEY`（API キー）に切り替えてください

**API キーが無効と言われる**

- キーが正しくコピーされているか確認（先頭の `sk-ant-` を含む）
- Console でキーが削除・無効化されていないか確認
- 支払い情報・クレジットが未設定の場合、Console の Billing から設定が必要

---

## 補足：サブスクリプションで動かしたい場合

Claude Pro / Max サブスクリプションの枠で動かす唯一の方法は、SDK での Messages API 直接呼び出しを
やめ、`claude` CLI のヘッドレスモード（`claude -p`）を `subprocess` 経由で呼ぶよう
`call_claude()` を書き換えることです。ただし以下のデメリットがあります。

- CLI のインストール・OAuth トークンの期限管理が必要
- サブスクのレート制限は対話用途向けで、複数エージェントの並列実行には不向き
- 個人アカウント紐付けのトークンのため、ECS 等のサーバーデプロイには適さない

サーバーデプロイや拡張性を考えると `ANTHROPIC_API_KEY` の利用を推奨します。
