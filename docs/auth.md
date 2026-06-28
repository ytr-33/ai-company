# 認証トークン取得手順

AI Company が Claude API を呼び出すために必要な認証情報の取得方法をまとめます。
`.env.example` をコピーして `.env` を作成し、以下のいずれか 1 つを設定してください。

```bash
cp .env.example .env
```

---

## 方法1: API キー（`ANTHROPIC_API_KEY`）

Anthropic コンソールから発行するキーです。課金はトークン使用量に応じた従量制です。

### 取得手順

1. [Anthropic Console](https://console.anthropic.com) にアクセスしてアカウントを作成またはサインインする
2. 左メニューの **API Keys** を開く
3. **+ Create Key** ボタンをクリックして新しいキーを作成する
4. 表示されたキー（`sk-ant-...`）をコピーする（再表示されないため必ずこの時点で保存）

### `.env` への設定

```env
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxx
```

### 注意事項

- キーは作成直後にしか表示されません。紛失した場合は再発行が必要です
- キーに使用量制限（Spending Limit）を設定することを推奨します（Console → Settings → Limits）
- キーを Git にコミットしないでください（`.env` は `.gitignore` に含まれています）

---

## 方法2: OAuth トークン（`CLAUDE_CODE_OAUTH_TOKEN`）

Claude Code CLI が発行する長期トークンです。Claude のサブスクリプション（Pro 以上）が必要です。
API キーと異なり、サブスクリプション料金の範囲内で使えます。

### 前提条件

- Claude Pro / Team / Enterprise サブスクリプション
- Claude Code CLI のインストール

```bash
# Claude Code CLI のインストール（未インストールの場合）
npm install -g @anthropic-ai/claude-code
```

### 取得手順

1. ターミナルで以下を実行する

   ```bash
   claude setup-token
   ```

2. ブラウザが開き、Anthropic への OAuth 認証を求められる
3. サインインして「許可」をクリックする
4. ターミナルにトークンが表示されるのでコピーする

### `.env` への設定

```env
CLAUDE_CODE_OAUTH_TOKEN=oauth-xxxxxxxxxxxxxxxxxxxxxxxx
```

### 注意事項

- サブスクリプションがない場合はこの方法は使えません
- トークンは有効期限が長いですが、期限切れの場合は `claude setup-token` を再実行してください

---

## 方法3: OAuth Bearer トークン（`ANTHROPIC_AUTH_TOKEN`）

`CLAUDE_CODE_OAUTH_TOKEN` と同じ OAuth トークンを別の環境変数名で設定する方法です。
用途や値に違いはありません。Claude Code CLI 以外のツールが発行したトークンを使う場合にこちらを使います。

### `.env` への設定

```env
ANTHROPIC_AUTH_TOKEN=oauth-xxxxxxxxxxxxxxxxxxxxxxxx
```

---

## 優先順位

複数の環境変数が設定されている場合、`base_agent.py` は以下の順で認証情報を使用します。

```
ANTHROPIC_API_KEY  >  ANTHROPIC_AUTH_TOKEN  >  CLAUDE_CODE_OAUTH_TOKEN
```

---

## どれを選ぶか

| 状況 | 推奨 |
|---|---|
| 個人・検証・従量制で使いたい | `ANTHROPIC_API_KEY` |
| Claude Pro / Team に加入済みで追加費用を避けたい | `CLAUDE_CODE_OAUTH_TOKEN` |
| CI/CD など自動化環境で使う | `ANTHROPIC_API_KEY`（シークレット管理しやすい） |

---

## トラブルシュート

**`No auth configured` エラーが出る**

`.env` に認証情報が設定されていないか、変数名が間違っています。`logs/ceo.log` などを確認してください。

```bash
cat logs/ceo.log | grep -i auth
```

**API キーが無効と言われる**

- キーが正しくコピーされているか確認（先頭の `sk-ant-` を含む）
- Console でキーが削除・無効化されていないか確認
- 支払い情報が未設定の場合、Console の Billing から設定が必要

**OAuth トークンが期限切れ**

```bash
claude setup-token   # 再実行してトークンを更新
```
