# AI Company 要件定義書

## 1. システム概要

複数の AI エージェントが役割分担しながら協調し、ユーザーのソフトウェア開発依頼を自動的に遂行するシステム。エージェント間通信はファイルベースの JSON メッセージングで行い、外部ミドルウェア（メッセージキュー・DB）を必要としない。

---

## 2. 背景・目的

- 自然言語で開発依頼を入力するだけで、設計・実装・レビューまでを AI エージェント群が完結させる
- 人間の介入ポイントを「要件の確認」と「完了通知の受領」のみに絞る
- ローカル環境・クラウド環境どちらでも同じコードで動作させる

---

## 3. エージェント構成

| エージェント | ファイル | 役割 |
|---|---|---|
| CEO | `agents/ceo.py` | 要件定義・ユーザー対話・エスカレーション対応・完了報告 |
| Architect | `agents/architect.py` | 技術設計・タスク分解・並列割り当て・進捗管理 |
| Developer1 | `agents/developer.py developer1` | コード実装・差し戻し対応 |
| Developer2 | `agents/developer.py developer2` | コード実装・差し戻し対応（並列） |
| Reviewer | `agents/reviewer.py` | コードレビュー・差し戻し判定・エスカレーション判定 |

---

## 4. ワークフロー

```
ユーザー (CLI)
    │ user_task
    ▼
  CEO ──── 要件不明な場合 ──→ ceo_question → ユーザーが user_answer で回答（繰り返し可）
    │ design_request（仕様書）
    ▼
Architect
    │ assign_task（依存関係が解消されたタスクから順次）
    ├──────────────────────┐
    ▼                      ▼
Developer1             Developer2  ← 並列実装
    │ review_request        │ review_request
    └──────────┬────────────┘
               ▼
           Reviewer
          ┌────┴─────┐
      approved    rejected（最大3回）
          │             │
          │ task_done   │ revision_request → Developer（差し戻し）
          │             └── 3回失敗 → escalation → CEO → revised_instruction → Architect
          ▼
      Architect（全タスク完了？）
          │ task_complete
          ▼
        CEO
          │ notify_completion / user_response.json
          ▼
       ユーザー (CLI)
```

---

## 5. エージェント間メッセージ仕様

### 5.1 メッセージ共通フォーマット

```json
{
  "id": "<uuid>",
  "from": "<送信者名>",
  "to": "<受信者名>",
  "type": "<メッセージ種別>",
  "content": "<本文>",
  "timestamp": "<ISO 8601 UTC>"
}
```

メッセージは `workspace/messages/inbox/<受信者名>.json` にリスト形式で追記される。

### 5.2 メッセージ種別一覧

| type | 送信者 → 受信者 | 追加フィールド | 説明 |
|---|---|---|---|
| `user_task` | CLI → CEO | — | 新規開発依頼 |
| `user_answer` | CLI → CEO | — | CEO の質問に対する回答 |
| `design_request` | CEO → Architect | `original_task` | 仕様書を渡して設計依頼 |
| `revised_instruction` | CEO → Architect | `task_id` | エスカレーション後の修正指示 |
| `assign_task` | Architect → Developer | `task_id`, `title`, `output_file`, `context`, `retry_count` | タスク割り当て |
| `review_request` | Developer → Reviewer | `task_id`, `file_path`, `code`, `notes`, `retry_count`, `developer` | レビュー依頼 |
| `revision_request` | Reviewer → Developer | `task_id`, `file_path`, `original_code`, `retry_count` | 差し戻し |
| `task_done` | Reviewer → Architect | `task_id`, `file_path` | レビュー承認通知 |
| `escalation` | Reviewer → CEO | `task_id`, `file_path`, `retry_count` | 3回失敗によるエスカレーション |
| `task_complete` | Architect → CEO | — | 全タスク完了通知 |

---

## 6. CEO エージェント仕様

### 6.1 入力メッセージ処理

| 受信 type | 処理 |
|---|---|
| `user_task` | 会話履歴を初期化し Claude に思考させる |
| `user_answer` | 会話履歴に追記し Claude に思考させる |
| `escalation` | エスカレーション内容を会話履歴に追記し Claude に思考させる |
| `task_complete` | `user_response.json` に完了通知を書き込む |

### 6.2 Claude レスポンス形式

```json
{
  "action": "ask_user | delegate_to_architect | respond_to_escalation | notify_completion",
  "questions": ["質問1"],
  "spec": "仕様書全文",
  "response": "エスカレーション対応内容",
  "summary": "完了サマリー"
}
```

---

## 7. Architect エージェント仕様

### 7.1 Claude レスポンス形式

```json
{
  "tech_stack": "使用技術",
  "file_structure": "ファイル構成",
  "design_doc": "設計ドキュメント全文",
  "tasks": [
    {
      "task_id": "T-001",
      "assignee": "developer1 | developer2",
      "title": "タスクタイトル",
      "description": "実装内容の詳細",
      "output_file": "src/xxx.py",
      "dependencies": ["T-001"],
      "context": "参考情報"
    }
  ]
}
```

### 7.2 タスク分解ルール

- タスク ID は `T-001`, `T-002` 形式
- assignee は `developer1` / `developer2` を交互に振り分ける
- `dependencies` に列挙された全タスクが完了するまで次タスクを送信しない
- 設計ドキュメントは `workspace/output/docs/design.md` に保存する

---

## 8. Developer エージェント仕様

### 8.1 Claude レスポンス形式

```json
{
  "file_path": "src/xxx.py",
  "code": "実装コード全文",
  "summary": "実装内容の要約",
  "notes": "実装上の注意点"
}
```

### 8.2 実装ルール

- 出力先: `workspace/output/<file_path>`
- 実装完了後、Reviewer に `review_request` を送信する
- 差し戻し（`revision_request`）を受けた場合は元コードとフィードバックを合わせて修正し、再度 `review_request` を送る

---

## 9. Reviewer エージェント仕様

### 9.1 Claude レスポンス形式

```json
{
  "verdict": "approved | rejected",
  "score": 1,
  "issues": ["問題点"],
  "feedback": "修正指示",
  "praise": "良かった点"
}
```

### 9.2 レビュー観点

1. 機能の正確性（要件充足）
2. エラーハンドリング（例外処理）
3. コードの可読性（命名・構造）
4. セキュリティ（SQLi・XSS 等）
5. パフォーマンス（明らかな問題）
6. 型ヒント・ドキュメント

### 9.3 判定フロー

- `approved` → Architect に `task_done` を送信
- `rejected` かつ `retry_count < 3` → Developer に `revision_request` を送信
- `rejected` かつ `retry_count >= 3` → CEO に `escalation` を送信

---

## 10. ファイル・ディレクトリ構成

```
workspace/
  messages/
    inbox/
      ceo.json          ← CEO 宛メッセージ（リスト形式 JSON）
      architect.json
      developer1.json
      developer2.json
      reviewer.json
    processed/
      <agent>_<ts>.json ← 処理済みメッセージのアーカイブ
  state/
    project.json        ← エージェント状態・タスク進捗（全エージェントが読み書き）
    task_log.jsonl      ← 全イベントログ（ダッシュボード用）
    user_response.json  ← CEO → CLI への応答ファイル（ポーリング用）
  output/
    src/                ← Developer が生成したソースコード
    docs/
      design.md         ← Architect が生成した設計ドキュメント
```

---

## 11. エージェント基底クラス（BaseAgent）

| メソッド | 説明 |
|---|---|
| `send_message(to, type, content, extra)` | `workspace/messages/inbox/<to>.json` にメッセージを追記 |
| `read_inbox()` | 自身の inbox を読み込み、`processed/` に移動してリターン |
| `call_claude(system, messages)` | Anthropic API を呼び出してテキストを返す |
| `log_event(event, detail)` | `task_log.jsonl` に追記しロガーに出力 |
| `update_state(key, value)` | `project.json` にキーを書き込む |
| `get_state()` | `project.json` を読み込んで返す |
| `run()` | watchdog でインボックスを監視し、メッセージが届いたら `process_inbox()` を呼ぶ |

---

## 12. 認証

Anthropic API の認証情報を以下の優先順位で解決する。

| 優先 | 環境変数 | 認証方式 |
|---|---|---|
| 1 | `ANTHROPIC_API_KEY` | API キー |
| 2 | `ANTHROPIC_AUTH_TOKEN` | OAuth Bearer トークン |
| 3 | `CLAUDE_CODE_OAUTH_TOKEN` | OAuth Bearer トークン（`claude setup-token` で取得） |

いずれも未設定の場合は起動時に `RuntimeError` を送出する。

---

## 13. ダッシュボード

| エンドポイント | 説明 |
|---|---|
| `GET /` | ダッシュボード HTML |
| `GET /api/state` | `project.json` の内容を返す |
| `GET /api/files` | `workspace/output/` 以下のファイル一覧を返す |
| `GET /api/logs` | `task_log.jsonl` の末尾 100 件を返す |
| `GET /api/logs/stream` | SSE でログをリアルタイム配信 |

起動コマンド: `uvicorn dashboard.server:app --host 0.0.0.0 --port 8080`

---

## 14. CLI

```
python3 cli/main.py "<依頼内容>"
```

- CEO に `user_task` メッセージを送信する
- `workspace/state/user_response.json` をポーリング（0.5 秒間隔、最大 180 秒）してレスポンスを待つ
- `ceo_question` を受信した場合はターミナルで回答を受け付け、`user_answer` を送信する
- `completion` を受信した場合は完了メッセージを表示して終了する

---

## 15. 起動手順

```bash
# .env を準備
cp .env.example .env
# ANTHROPIC_API_KEY または CLAUDE_CODE_OAUTH_TOKEN を設定

# 全エージェント + ダッシュボードを一括起動
bash run_local.sh

# 別ターミナルでタスク依頼
python3 cli/main.py "TODO REST API を FastAPI で作って"
```

---

## 16. 非機能要件

| 項目 | 内容 |
|---|---|
| LLM モデル | 環境変数 `MODEL` で指定（デフォルト: `claude-sonnet-4-6`） |
| LLM 最大トークン | 4096 tokens / 呼び出し |
| レビュー最大試行回数 | 3 回（`MAX_RETRIES = 3`） |
| CLI タイムアウト | 180 秒 |
| ログ形式 | JSONL（`task_log.jsonl`）+ Python `logging`（標準出力） |
| 外部依存ミドルウェア | なし（ファイルシステムのみ） |
