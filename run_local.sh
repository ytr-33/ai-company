#!/bin/bash
# ローカルでエージェントとダッシュボードを起動するスクリプト

set -e
cd "$(dirname "$0")"

export WORKSPACE_DIR="$(pwd)/workspace"
export PYTHONPATH="$(pwd)"

# .envが存在すれば読み込む
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

echo "=============================="
echo " AI Company - Local Runner"
echo " WORKSPACE: $WORKSPACE_DIR"
echo "=============================="

# ワークスペース初期化
mkdir -p "$WORKSPACE_DIR"/{messages/{inbox,processed},state,output/{src,docs}}
# *.json だけでなく排他ロック用の *.json.lock も初期化対象に含める
rm -f "$WORKSPACE_DIR"/messages/inbox/*.json*
rm -f "$WORKSPACE_DIR"/state/project.json
rm -f "$WORKSPACE_DIR"/state/task_log.jsonl
rm -f "$WORKSPACE_DIR"/state/user_response.json

# ログファイル
LOG_DIR="$(pwd)/logs"
mkdir -p "$LOG_DIR"

echo "🚀 エージェントを起動中..."

python3 agents/ceo.py       > "$LOG_DIR/ceo.log"       2>&1 &  CEO_PID=$!
python3 agents/architect.py > "$LOG_DIR/architect.log"  2>&1 &  ARCH_PID=$!
python3 agents/developer.py developer1 > "$LOG_DIR/dev1.log" 2>&1 & DEV1_PID=$!
python3 agents/developer.py developer2 > "$LOG_DIR/dev2.log" 2>&1 & DEV2_PID=$!
python3 agents/reviewer.py  > "$LOG_DIR/reviewer.log"  2>&1 &  REV_PID=$!

echo "📊 ダッシュボードを起動中 (http://localhost:8080)..."
uvicorn dashboard.server:app --host 0.0.0.0 --port 8080 \
  > "$LOG_DIR/dashboard.log" 2>&1 &  DASH_PID=$!

# 全プロセスをまとめてkillする関数
cleanup() {
  echo ""
  echo "🛑 停止中..."
  kill $CEO_PID $ARCH_PID $DEV1_PID $DEV2_PID $REV_PID $DASH_PID 2>/dev/null
  exit 0
}
trap cleanup SIGINT SIGTERM

echo ""
echo "✅ 起動完了！"
echo "  📊 ダッシュボード : http://localhost:8080"
echo "  📝 タスク依頼    : python3 cli/main.py \"タスク内容\""
echo "  📁 ログ         : logs/ ディレクトリ"
echo ""
echo "Ctrl+C で全プロセス終了"
echo ""

sleep 2

echo "--- エージェントログ (tail -f logs/*.log) ---"
tail -f "$LOG_DIR"/*.log
