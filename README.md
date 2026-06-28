# AI Company

複数のAIエージェントが協調してソフトウェア開発を行うシステムです。

## アーキテクチャ

```
ユーザー (CLI)
    ↓
  CEO      ← 要件定義・対話・エスカレーション対応
    ↓
Architect  ← 設計・タスク分解・並列割り当て
   ↙ ↘
Dev1  Dev2  ← 並列実装
   ↘ ↙
Reviewer   ← コードレビュー（最大3回、失敗時はCEOへ）
    ↓
  成果物 (workspace/output/)
```

## エージェント通信

テキストファイル（JSON）を介してメッセージ交換します：

```
workspace/
  messages/inbox/    ← 各エージェントのメールボックス
  messages/processed/← 処理済みメッセージ
  state/
    project.json     ← プロジェクト状態
    task_log.jsonl   ← 全イベントログ（ダッシュボード用）
  output/
    src/             ← 生成コード
    docs/            ← 生成ドキュメント
```

## 認証

各エージェントは OpenAI の Chat Completions API を呼ぶため、**API キー（`OPENAI_API_KEY`）が必要**です。

```bash
cp .env.example .env
```

| 環境変数 | 用途 | 取得方法 |
|---|---|---|
| `OPENAI_API_KEY` | API キー（必須、要クレジット） | https://platform.openai.com |
| `OPENAI_BASE_URL` | カスタムエンドポイント（任意。OpenRouter / LiteLLM / vLLM 等の互換 API） | — |

詳細な取得手順・トラブルシュートは [docs/auth.md](docs/auth.md) を参照してください。

`MODEL`（既定 `gpt-4o`）でモデルを切り替えられます。

## ローカルで実行する（推奨）

Docker 不要。`run_local.sh` が全エージェント＋ダッシュボードを 1 プロセスずつ起動し、
すべて同じ `./workspace` を共有します。

### 1. 準備

```bash
# 依存をインストール（venv 推奨）
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 認証情報を .env に設定（上記「認証」参照）
cp .env.example .env
$EDITOR .env
```

### 2. 起動

```bash
bash run_local.sh
```

起動すると以下が立ち上がります。

- CEO / Architect / Developer1 / Developer2 / Reviewer の5エージェント（常駐）
- ダッシュボード: http://localhost:8080
- 各プロセスのログ: `logs/*.log`

`run_local.sh` は起動時に `./workspace` の inbox / state を初期化します。
停止は起動したターミナルで `Ctrl+C`（全プロセスを一括 kill）。

### 3. タスクを依頼する（別ターミナル）

```bash
# 同じディレクトリで、workspace を合わせて実行
export WORKSPACE_DIR="$(pwd)/workspace"
python3 cli/main.py "TODO REST API を FastAPI で作って"
```

- CEO から確認質問が返ってきたらターミナルで回答（対話的に進行）
- 完了すると成果物が `workspace/output/`（`src/` と `docs/design.md`）に出力されます
- 進行状況はダッシュボード（http://localhost:8080）でリアルタイムに確認できます

### 4. 動作確認・トラブルシュート

```bash
tail -f logs/*.log              # 全エージェントのログを追う
cat workspace/state/project.json # 各エージェントの状態・タスク進捗
```

- `No auth configured` で各エージェントが落ちる → `.env` の認証情報が未設定。`logs/ceo.log` 等を確認
- CLI が「タイムアウト」になる → エージェントが起動しているか、`WORKSPACE_DIR` が一致しているか確認
- やり直したいとき → `Ctrl+C` で停止し、再度 `bash run_local.sh`（workspace は自動初期化）

## Docker で実行する

```bash
cp .env.example .env      # 認証情報を設定

make up          # 全コンテナ起動
make cli         # タスクを依頼
# ブラウザで http://localhost:8080 を開くとダッシュボード表示

make down        # 停止
make clean       # 完全クリーン
```

> ⚠️ 現状 `make up`（Docker の名前付きボリューム）と `make cli`（ホストの `./workspace`）は
> ワークスペースが別物のため、そのままでは CLI のメッセージが届きません（`Makefile` のコメント参照）。
> Docker 構成で使う場合は CLI もコンテナ内で実行するか、bind mount に変更してください。
> 手軽に試すなら上記の **ローカル実行** を推奨します。

## ワークフロー

1. `make cli` でタスクを入力
2. CEOが要件を確認（不明点があれば質問）
3. Architectが設計・タスク分解
4. Developer1・Developer2が並列実装
5. Reviewerがレビュー（NG→差し戻し、3回失敗→CEOへエスカレ）
6. 全タスク完了でCEOが報告