.PHONY: up down logs cli clean

up:
	docker compose up --build -d
	@echo "\n✅ 全エージェント起動完了"
	@echo "📊 ダッシュボード: http://localhost:8080\n"

down:
	docker compose down

logs:
	docker compose logs -f

# FIXME(ワークスペース不一致): `make up` は docker-compose の名前付きボリューム
#   `workspace`（/var/lib/docker 配下）を使うが、この `cli` ターゲットはホストの
#   ./workspace を見るため、Docker 上のエージェントとメッセージを共有できない。
#   Docker 利用時は CLI もコンテナ内で実行するか（例: docker compose run）、
#   docker-compose 側を bind mount（./workspace:/workspace）に変更して揃える必要がある。
#   ローカル一括起動（run_local.sh）なら全プロセスが ./workspace を共有するため問題ない。
cli:
	@WORKSPACE_DIR=./workspace python cli/main.py

clean:
	docker compose down -v
	rm -rf workspace/messages workspace/state workspace/output
	mkdir -p workspace/messages/inbox workspace/messages/processed workspace/state workspace/output/src workspace/output/docs

dev-dashboard:
	WORKSPACE_DIR=./workspace uvicorn dashboard.server:app --host 0.0.0.0 --port 8080 --reload
