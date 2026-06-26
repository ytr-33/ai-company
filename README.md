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

## セットアップ

```bash
cp .env.example .env
# .env に ANTHROPIC_API_KEY を設定

make up          # 全コンテナ起動
make cli         # タスクを依頼
# ブラウザで http://localhost:8080 を開くとダッシュボード表示

make down        # 停止
make clean       # 完全クリーン
```

## ワークフロー

1. `make cli` でタスクを入力
2. CEOが要件を確認（不明点があれば質問）
3. Architectが設計・タスク分解
4. Developer1・Developer2が並列実装
5. Reviewerがレビュー（NG→差し戻し、3回失敗→CEOへエスカレ）
6. 全タスク完了でCEOが報告