"""Mock Claude API for local testing without an API key."""
import json
import random
import time


MOCK_RESPONSES = {
    "ceo": {
        "ask_user": json.dumps({
            "action": "ask_user",
            "questions": [
                "どのプログラミング言語を使用しますか？（Python / TypeScript / Go）",
                "認証機能は必要ですか？",
                "データベースは何を使いますか？（SQLite / PostgreSQL / MySQL）"
            ]
        }, ensure_ascii=False),
        "delegate": json.dumps({
            "action": "delegate_to_architect",
            "spec": """## プロジェクト仕様書

### 概要
シンプルなTODO管理REST APIの開発

### 技術スタック
- 言語: Python
- フレームワーク: FastAPI
- DB: SQLite

### 機能要件
1. TODO一覧取得 GET /todos
2. TODO作成 POST /todos
3. TODO更新 PUT /todos/{id}
4. TODO削除 DELETE /todos/{id}

### 非機能要件
- エラーハンドリング必須
- 型ヒント必須
- APIドキュメント自動生成（FastAPI標準）
"""
        }, ensure_ascii=False)
    },
    "architect": json.dumps({
        "tech_stack": "Python 3.12 + FastAPI + SQLite + SQLAlchemy",
        "file_structure": """todo-api/
  main.py       - FastAPIアプリエントリポイント
  models.py     - SQLAlchemyモデル定義
  database.py   - DB接続・セッション管理
  schemas.py    - Pydanticスキーマ
  requirements.txt""",
        "design_doc": "シンプルなCRUD REST APIをFastAPIで実装します。",
        "tasks": [
            {
                "task_id": "T-001",
                "assignee": "developer1",
                "title": "database.py + models.py の実装",
                "description": "SQLiteのDB接続設定とSQLAlchemyモデルを実装してください。TodoモデルはID・タイトル・完了フラグ・作成日時を持ちます。",
                "output_file": "src/database.py",
                "dependencies": [],
                "context": "SQLAlchemy 2.0スタイルで記述すること"
            },
            {
                "task_id": "T-002",
                "assignee": "developer2",
                "title": "schemas.py の実装",
                "description": "PydanticのスキーマをTodoCreate・TodoUpdate・TodoResponseとして定義してください。",
                "output_file": "src/schemas.py",
                "dependencies": [],
                "context": "Pydantic v2スタイルで記述すること"
            },
            {
                "task_id": "T-003",
                "assignee": "developer1",
                "title": "main.py の実装",
                "description": "FastAPIのメインファイルにCRUDエンドポイントを実装してください。",
                "output_file": "src/main.py",
                "dependencies": ["T-001", "T-002"],
                "context": "エラーハンドリングを適切に行うこと"
            }
        ]
    }, ensure_ascii=False),
    "developer_database": json.dumps({
        "file_path": "src/database.py",
        "code": '''"""Database connection and session management."""
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone

DATABASE_URL = "sqlite:///./todos.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Todo(Base):
    __tablename__ = "todos"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    completed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


Base.metadata.create_all(bind=engine)
''',
        "summary": "SQLiteのDB接続とTodoモデルを実装しました",
        "notes": ""
    }, ensure_ascii=False),
    "developer_schemas": json.dumps({
        "file_path": "src/schemas.py",
        "code": '''"""Pydantic schemas for request/response validation."""
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class TodoCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200, description="TODOのタイトル")


class TodoUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    completed: Optional[bool] = None


class TodoResponse(BaseModel):
    id: int
    title: str
    completed: bool
    created_at: datetime

    model_config = {"from_attributes": True}
''',
        "summary": "TodoCreate, TodoUpdate, TodoResponseスキーマを実装しました",
        "notes": ""
    }, ensure_ascii=False),
    "developer_main": json.dumps({
        "file_path": "src/main.py",
        "code": '''"""FastAPI TODO application entry point."""
from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from database import get_db, Todo
from schemas import TodoCreate, TodoUpdate, TodoResponse

app = FastAPI(title="TODO API", version="1.0.0", description="シンプルなTODO管理API")


@app.get("/todos", response_model=List[TodoResponse])
def list_todos(db: Session = Depends(get_db)):
    """TODO一覧を取得します。"""
    return db.query(Todo).all()


@app.post("/todos", response_model=TodoResponse, status_code=status.HTTP_201_CREATED)
def create_todo(todo: TodoCreate, db: Session = Depends(get_db)):
    """新しいTODOを作成します。"""
    db_todo = Todo(title=todo.title)
    db.add(db_todo)
    db.commit()
    db.refresh(db_todo)
    return db_todo


@app.put("/todos/{todo_id}", response_model=TodoResponse)
def update_todo(todo_id: int, todo: TodoUpdate, db: Session = Depends(get_db)):
    """TODOを更新します。"""
    db_todo = db.query(Todo).filter(Todo.id == todo_id).first()
    if not db_todo:
        raise HTTPException(status_code=404, detail="TODOが見つかりません")
    if todo.title is not None:
        db_todo.title = todo.title
    if todo.completed is not None:
        db_todo.completed = todo.completed
    db.commit()
    db.refresh(db_todo)
    return db_todo


@app.delete("/todos/{todo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_todo(todo_id: int, db: Session = Depends(get_db)):
    """TODOを削除します。"""
    db_todo = db.query(Todo).filter(Todo.id == todo_id).first()
    if not db_todo:
        raise HTTPException(status_code=404, detail="TODOが見つかりません")
    db.delete(db_todo)
    db.commit()
''',
        "summary": "FastAPI CRUDエンドポイントを実装しました",
        "notes": ""
    }, ensure_ascii=False),
    "reviewer_approved": json.dumps({
        "verdict": "approved",
        "score": 8,
        "issues": [],
        "feedback": "",
        "praise": "型ヒントが適切で、エラーハンドリングも実装されています。コードが読みやすく整理されています。"
    }, ensure_ascii=False),
}


def get_mock_response(agent_name: str, context: str = "") -> str:
    time.sleep(random.uniform(0.5, 1.5))  # simulate API latency

    if agent_name == "ceo":
        # first call asks questions, second call delegates
        if "回答" in context or "answer" in context.lower():
            return MOCK_RESPONSES["ceo"]["delegate"]
        return MOCK_RESPONSES["ceo"]["ask_user"]

    if agent_name == "architect":
        return MOCK_RESPONSES["architect"]

    if agent_name in ("developer1", "developer2"):
        if "database" in context.lower() or "T-001" in context:
            return MOCK_RESPONSES["developer_database"]
        elif "schema" in context.lower() or "T-002" in context:
            return MOCK_RESPONSES["developer_schemas"]
        else:
            return MOCK_RESPONSES["developer_main"]

    if agent_name == "reviewer":
        return MOCK_RESPONSES["reviewer_approved"]

    return json.dumps({"result": "ok"})
