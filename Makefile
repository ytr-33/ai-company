.PHONY: up down logs cli clean

up:
	docker compose up --build -d
	@echo "\n✅ 全エージェント起動完了"
	@echo "📊 ダッシュボード: http://localhost:8080\n"

down:
	docker compose down

logs:
	docker compose logs -f

cli:
	@WORKSPACE_DIR=./workspace python cli/main.py

clean:
	docker compose down -v
	rm -rf workspace/messages workspace/state workspace/output
	mkdir -p workspace/messages/inbox workspace/messages/processed workspace/state workspace/output/src workspace/output/docs

dev-dashboard:
	WORKSPACE_DIR=./workspace uvicorn dashboard.server:app --host 0.0.0.0 --port 8080 --reload
