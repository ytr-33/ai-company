import json
import os
import time
import uuid
import fcntl
import logging
import contextlib
from pathlib import Path
from datetime import datetime, timezone
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import anthropic

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class InboxHandler(FileSystemEventHandler):
    def __init__(self, agent):
        self.agent = agent

    def on_created(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.name == f"{self.agent.name}.json":
            time.sleep(0.1)  # wait for write to complete
            self.agent.process_inbox()

    def on_modified(self, event):
        self.on_created(event)


class BaseAgent:
    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(name.upper())
        self.workspace = Path(os.getenv("WORKSPACE_DIR", "/workspace"))
        self.inbox_dir = self.workspace / "messages" / "inbox"
        self.processed_dir = self.workspace / "messages" / "processed"
        self.state_dir = self.workspace / "state"
        self.output_dir = self.workspace / "output"
        self.client = self._build_client()
        self.model = os.getenv("MODEL", "claude-sonnet-4-6")

        for d in [self.inbox_dir, self.processed_dir, self.state_dir,
                  self.output_dir / "src", self.output_dir / "docs"]:
            d.mkdir(parents=True, exist_ok=True)

    def _build_client(self) -> anthropic.Anthropic:
        # Priority: ANTHROPIC_API_KEY > ANTHROPIC_AUTH_TOKEN > CLAUDE_CODE_OAUTH_TOKEN
        api_key = os.getenv("ANTHROPIC_API_KEY")
        auth_token = os.getenv("ANTHROPIC_AUTH_TOKEN") or os.getenv("CLAUDE_CODE_OAUTH_TOKEN")
        if api_key:
            return anthropic.Anthropic(api_key=api_key)
        if auth_token:
            return anthropic.Anthropic(auth_token=auth_token)
        raise RuntimeError(
            "No auth configured. Set ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN, "
            "or CLAUDE_CODE_OAUTH_TOKEN in .env"
        )

    @contextlib.contextmanager
    def _inbox_lock(self, name: str):
        # 宛先ごとの専用ロックファイル（<name>.json.lock）に対して排他ロックを取る。
        # inbox 本体（<name>.json）は read_inbox で rename/削除されるため、
        # ロック対象には常に存在する安定したロックファイルを使う。
        lock_path = self.inbox_dir / f"{name}.json.lock"
        lock_file = open(lock_path, "a+")
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            lock_file.close()

    def send_message(self, to: str, msg_type: str, content: str, extra: dict = None):
        msg = {
            "id": str(uuid.uuid4()),
            "from": self.name,
            "to": to,
            "type": msg_type,
            "content": content,
            "timestamp": utcnow(),
        }
        if extra:
            msg.update(extra)
        inbox_path = self.inbox_dir / f"{to}.json"
        # 対応済み(書き込み競合): 宛先ごとのロックファイルで排他ロックを取り、
        #   read-modify-write をアトミックに行う。同じ宛先への同時送信でも取りこぼさない。
        with self._inbox_lock(to):
            messages = []
            if inbox_path.exists():
                try:
                    messages = json.loads(inbox_path.read_text())
                except Exception:
                    messages = []
            messages.append(msg)
            inbox_path.write_text(json.dumps(messages, ensure_ascii=False, indent=2))
        self.log_event("message_sent", f"→ [{to}] {msg_type}: {content[:80]}")
        return msg["id"]

    def read_inbox(self) -> list[dict]:
        inbox_path = self.inbox_dir / f"{self.name}.json"
        # 対応済み(取りこぼし競合): 自分宛のロックを取った状態で「読み込み → inbox を空にする」
        #   までを行い、その隙間に send_message が割り込めないようにする。
        #   ロック内で rename 済みのため、以降の追記は新しい inbox ファイルへ入り再発火で拾える。
        with self._inbox_lock(self.name):
            if not inbox_path.exists():
                return []
            try:
                messages = json.loads(inbox_path.read_text())
                processed_path = self.processed_dir / f"{self.name}_{utcnow().replace(':','').replace('.','')}.json"
                inbox_path.rename(processed_path)
                return messages
            except Exception:
                return []

    def log_event(self, event: str, detail: str):
        entry = {
            "ts": utcnow(),
            "agent": self.name,
            "event": event,
            "detail": detail,
        }
        log_path = self.state_dir / "task_log.jsonl"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self.logger.info(f"[{event}] {detail}")

    def update_state(self, key: str, value):
        state_path = self.state_dir / "project.json"
        state = {}
        if state_path.exists():
            try:
                state = json.loads(state_path.read_text())
            except Exception:
                pass
        state[key] = value
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2))

    def get_state(self) -> dict:
        state_path = self.state_dir / "project.json"
        if not state_path.exists():
            return {}
        try:
            return json.loads(state_path.read_text())
        except Exception:
            return {}

    def call_claude(self, system: str, messages: list[dict]) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system,
            messages=messages,
        )
        return response.content[0].text

    def process_inbox(self):
        raise NotImplementedError

    def run(self):
        self.log_event("agent_start", f"{self.name} agent started")
        self.update_state(f"agent_{self.name}_status", "waiting")

        observer = Observer()
        handler = InboxHandler(self)
        observer.schedule(handler, str(self.inbox_dir), recursive=False)
        observer.start()

        try:
            self.process_inbox()
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            observer.stop()
            observer.join()
