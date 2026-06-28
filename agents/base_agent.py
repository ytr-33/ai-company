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
import openai

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
        self.model = os.getenv("MODEL", "gpt-4o")

        for d in [self.inbox_dir, self.processed_dir, self.state_dir,
                  self.output_dir / "src", self.output_dir / "docs"]:
            d.mkdir(parents=True, exist_ok=True)

    def _build_client(self) -> openai.OpenAI:
        # max_retries=0: 429 のリトライは call_claude の指数バックオフに一元化する
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("No auth configured. Set OPENAI_API_KEY in .env")
        base_url = os.getenv("OPENAI_BASE_URL")  # カスタムエンドポイント（任意）
        kwargs = {"api_key": api_key, "max_retries": 0}
        if base_url:
            kwargs["base_url"] = base_url
        return openai.OpenAI(**kwargs)

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
        # OpenAI Chat Completions を呼ぶ。メソッド名は各エージェントとの互換のため維持。
        # SDK の自動リトライは無効化（_build_client で max_retries=0）し、
        # ここで Retry-After ヘッダ優先・指数バックオフ（最大 5 回）を一元管理する。
        # ベース待機を 60s にするのは TPM のリセット窓が 60s のため。
        max_retries = 5
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    # gpt-4o は max_tokens で可。o系/gpt-5系へ変える場合は max_completion_tokens が必要
                    max_tokens=4096,
                    messages=[{"role": "system", "content": system}, *messages],
                )
                return response.choices[0].message.content or ""
            except openai.RateLimitError as e:
                if attempt == max_retries - 1:
                    raise
                # Retry-After ヘッダを優先
                retry_after = None
                if hasattr(e, "response") and e.response is not None:
                    retry_after = e.response.headers.get("retry-after")
                wait = float(retry_after) if retry_after else 60.0 * (2 ** attempt)
                self.log_event(
                    "rate_limit_retry",
                    f"429 レートリミット。{wait:.0f}秒後に再試行 ({attempt + 1}/{max_retries})"
                )
                time.sleep(wait)

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
