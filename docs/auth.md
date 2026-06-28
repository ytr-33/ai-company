# 認証トークン取得手順

AI Company が OpenAI API を呼び出すために必要な認証情報の取得方法をまとめます。

## このシステムは OpenAI の「API キー」が必要です

各エージェント（`agents/base_agent.py`）は OpenAI の **Chat Completions API** を呼び出します。
そのため、**`OPENAI_API_KEY`（API キー）** を設定してください。

```bash
cp .env.example .env
```

---

## API キー（`OPENAI_API_KEY`）

OpenAI のプラットフォームから発行するキーです。課金は使用量に応じた従量制で、**API クレジット**が必要です。

### 取得手順

1. [OpenAI Platform](https://platform.openai.com) にアクセスしてサインインする
2. **API クレジットを購入する / 支払い方法を設定する**（残高 0 だと 429 エラーになります）
   - Settings → Billing から設定できます
3. 左メニューの **API keys** を開く
4. **+ Create new secret key** をクリックして新しいキーを作成する
5. 表示されたキー（`sk-...`）をコピーする（再表示されないため必ずこの時点で保存）

### `.env` への設定

```env
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxx
```

### 注意事項

- キーは作成直後にしか表示されません。紛失した場合は再発行が必要です
- キーに使用量上限（Usage limits）を設定することを推奨します（Settings → Limits）
- キーを Git にコミットしないでください（`.env` は `.gitignore` に含まれています）

---

## カスタムエンドポイント（`OPENAI_BASE_URL`、任意）

OpenAI 互換 API（OpenRouter / LiteLLM / vLLM など）を使う場合に、エンドポイントを上書きできます。

```env
OPENAI_BASE_URL=https://openrouter.ai/api/v1
```

> Azure OpenAI は素の `openai.OpenAI(base_url=...)` では動作しません（`AzureOpenAI` クラスや
> `api-version` 付き URL・デプロイ名が必要）。利用する場合は別途コード対応が必要です。

---

## モデルの指定（`MODEL`）

`.env` の `MODEL` で使用するモデルを切り替えられます（既定 `gpt-4o`）。

```env
MODEL=gpt-4o
```

> **注意：** `gpt-4o` は `max_tokens` パラメータで動作します。o 系（reasoning）モデルや
> gpt-5 系など新しいモデルに切り替える場合、`max_tokens` ではなく `max_completion_tokens` が
> 必要になり、現状のコードのままでは 400 エラーになります。その場合は
> `agents/base_agent.py` の `call_claude()` の `max_tokens` 部分を修正してください。

---

## トラブルシュート

**`No auth configured` エラーが出る**

`.env` に `OPENAI_API_KEY` が設定されていないか、変数名が間違っています。`logs/ceo.log` などを確認してください。

```bash
cat logs/ceo.log | grep -i auth
```

**429 Too Many Requests が出る**

- **最も多い原因は API クレジットの残高 0 / 支払い方法未設定**です。OpenAI Platform の Billing を確認してください
- 残高があるのに出る場合はレート制限（TPM/RPM）超過です。しばらく待つか、利用 Tier を確認してください
- `call_claude()` は指数バックオフで最大5回まで自動リトライします（`logs` に `rate_limit_retry` として記録）

**`max_tokens` 関連の 400 エラーが出る**

- `MODEL` を o 系・gpt-5 系などに変更した場合、`max_tokens` が使えません。上記「モデルの指定」を参照

**API キーが無効と言われる**

- キーが正しくコピーされているか確認（先頭の `sk-` を含む）
- Platform でキーが削除・無効化されていないか確認
- 支払い情報・クレジットが未設定の場合、Billing から設定が必要
