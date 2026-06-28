#!/usr/bin/env python3
"""CLI entry point for the AI Company."""
import json
import os
import sys
import time
import uuid
from pathlib import Path

import click
from dotenv import load_dotenv

load_dotenv()

WORKSPACE_DIR = Path(os.getenv("WORKSPACE_DIR", "./workspace"))
INBOX_DIR = WORKSPACE_DIR / "messages" / "inbox"
STATE_DIR = WORKSPACE_DIR / "state"


def send_to_ceo(msg_type: str, content: str, extra: dict = None):
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    msg = {
        "id": str(uuid.uuid4()),
        "from": "user",
        "to": "ceo",
        "type": msg_type,
        "content": content,
        # NOTE: datetime.utcnow() は Python 3.12 で非推奨。
        #   datetime.now(timezone.utc).isoformat() に置き換えるのが望ましい。
        "timestamp": __import__("datetime").datetime.utcnow().isoformat(),
    }
    if extra:
        msg.update(extra)

    inbox_path = INBOX_DIR / "ceo.json"
    messages = []
    if inbox_path.exists():
        try:
            messages = json.loads(inbox_path.read_text())
        except Exception:
            messages = []
    messages.append(msg)
    inbox_path.write_text(json.dumps(messages, ensure_ascii=False, indent=2))


def wait_for_ceo_response(timeout: int = 120) -> dict | None:
    # NOTE(応答の取りこぼし): user_response.json は CEO が上書き／CLI が読んで削除する単一ファイル。
    #   CEO が短時間に複数応答を書くと前の応答が読まれる前に上書きされ得る。
    #   また「送信直後に古い応答を削除」する作り（下記 unlink）のため、CEO が即応答すると
    #   正規の応答を削除してしまう競合もある。対話が逐次的な前提で成立しているだけ。
    #   対策: メッセージキュー（追記式 JSONL）+ 既読オフセット管理にする。
    response_path = STATE_DIR / "user_response.json"
    # clear old response
    if response_path.exists():
        response_path.unlink()

    deadline = time.time() + timeout
    while time.time() < deadline:
        if response_path.exists():
            try:
                data = json.loads(response_path.read_text())
                response_path.unlink()
                return data
            except Exception:
                pass
        time.sleep(0.5)
    return None


@click.command()
@click.argument("task", required=False)
@click.option("--interactive", "-i", is_flag=True, help="対話モード")
def main(task, interactive):
    """AI会社にソフトウェア開発タスクを依頼する CLI"""
    if not task:
        task = click.prompt("\n依頼内容を入力してください")

    click.echo(f"\n📨 [あなた → CEO] {task}")
    send_to_ceo("user_task", task)

    click.echo("⏳ CEOが要件を確認中...")

    # dialogue loop
    while True:
        response = wait_for_ceo_response(timeout=180)
        if response is None:
            click.echo("⚠️  タイムアウト: CEOからの応答がありませんでした。エージェントが起動しているか確認してください。")
            sys.exit(1)

        resp_type = response.get("type")

        if resp_type == "ceo_question":
            content = response.get("content", "")
            click.echo(f"\n💬 [CEO → あなた]\n{content}\n")
            answer = click.prompt("回答")
            click.echo(f"\n📨 [あなた → CEO] {answer}")
            send_to_ceo("user_answer", answer)
            click.echo("⏳ CEOが処理中...")

        elif resp_type == "completion":
            click.echo(f"\n✅ 完了!\n{response.get('content','')}\n")
            click.echo("📁 成果物は workspace/output/ に保存されています。")
            break

        else:
            click.echo(f"\n📣 [{resp_type}] {response.get('content','')}")
            break


if __name__ == "__main__":
    main()
