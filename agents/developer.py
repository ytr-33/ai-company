import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agents.base_agent import BaseAgent

SYSTEM_PROMPT = """あなたはAIソフトウェア開発会社のSenior Developerです。
Architectからタスクを受け取り、高品質なコードを実装します。

あなたの役割:
1. タスクの要件を理解する
2. 指定されたファイルにコードを実装する
3. 適切なエラーハンドリング・型ヒント・docstringを含める
4. 実装したコードの内容をReviewerに報告する

レスポンス形式（JSONで返すこと）:
{
  "file_path": "実装ファイルのパス（例: src/main.py）",
  "code": "実装したコードの全文",
  "summary": "実装内容の要約（Reviewerへの説明）",
  "notes": "実装上の注意点・懸念点（あれば）"
}"""


class DeveloperAgent(BaseAgent):
    def __init__(self, agent_name: str):
        super().__init__(agent_name)

    def process_inbox(self):
        messages = self.read_inbox()
        for msg in messages:
            self._handle_message(msg)

    def _handle_message(self, msg: dict):
        msg_type = msg.get("type")
        content = msg.get("content", "")
        sender = msg.get("from", "")

        self.log_event("message_received", f"← [{sender}] {msg_type}")
        self.update_state(f"agent_{self.name}_status", "working")

        if msg_type == "assign_task":
            self._handle_task(content, msg)
        elif msg_type == "revision_request":
            self._handle_revision(content, msg)

        self.update_state(f"agent_{self.name}_status", "waiting")

    def _handle_task(self, description: str, msg: dict):
        task_id = msg.get("task_id", "T-???")
        output_file = msg.get("output_file", "src/output.py")
        context = msg.get("context", "")
        retry_count = msg.get("retry_count", 0)

        self.log_event("task_start", f"{task_id}: {description[:80]}")

        prompt = f"""以下のタスクを実装してください。

タスクID: {task_id}
出力ファイル: {output_file}
実装内容: {description}
"""
        if context:
            prompt += f"\n参考情報:\n{context}"

        result_text = self.call_claude(SYSTEM_PROMPT, [{"role": "user", "content": prompt}])

        # NOTE(JSON抽出が脆弱): 先頭"{"〜末尾"}"を切り出す方式。code フィールドに
        #   生コード（波括弧・改行・引用符）が入るため、LLM が JSON を厳密にエスケープ
        #   しないと json.loads が失敗しやすい。失敗時は全文を code として扱うフォールバックで
        #   救っているが、本来は output_config の structured outputs / tool use で型を強制すべき。
        #   （この抽出パターンは ceo.py / architect.py / reviewer.py にも同様に存在）
        try:
            start = result_text.find("{")
            end = result_text.rfind("}") + 1
            result = json.loads(result_text[start:end])
        except Exception:
            self.log_event("parse_error", "実装結果のパースに失敗")
            result = {"file_path": output_file, "code": result_text, "summary": "実装完了", "notes": ""}

        # write code to output
        code = result.get("code", "")
        file_path = result.get("file_path", output_file)
        # NOTE(パストラバーサル): LLM が返す file_path を検証せず output_dir に結合している。
        #   "../" や絶対パスが返ると output 配下の外へ書き込み得る。
        #   対策: 正規化後に output_dir 配下であることを検証する（resolve() + is_relative_to）。
        full_path = self.output_dir / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(code, encoding="utf-8")
        self.log_event("file_created", file_path)

        # send to reviewer
        self.send_message("reviewer", "review_request", result.get("summary", ""), {
            "task_id": task_id,
            "file_path": file_path,
            "code": code,
            "notes": result.get("notes", ""),
            "retry_count": retry_count,
            "developer": self.name,
        })

    def _handle_revision(self, feedback: str, msg: dict):
        task_id = msg.get("task_id", "T-???")
        file_path = msg.get("file_path", "")
        original_code = msg.get("original_code", "")
        retry_count = msg.get("retry_count", 0)

        self.log_event("revision_start", f"{task_id} 修正開始 (試行{retry_count+1}回目)")

        prompt = f"""以下のコードをレビューフィードバックに基づいて修正してください。

タスクID: {task_id}
ファイル: {file_path}

元のコード:
```
{original_code}
```

レビューフィードバック:
{feedback}

フィードバックの問題をすべて修正した新しいコードを返してください。"""

        result_text = self.call_claude(SYSTEM_PROMPT, [{"role": "user", "content": prompt}])

        try:
            start = result_text.find("{")
            end = result_text.rfind("}") + 1
            result = json.loads(result_text[start:end])
        except Exception:
            result = {"file_path": file_path, "code": result_text, "summary": "修正完了", "notes": ""}

        code = result.get("code", "")
        full_path = self.output_dir / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(code, encoding="utf-8")
        self.log_event("file_updated", f"{file_path} 修正完了")

        self.send_message("reviewer", "review_request", result.get("summary", "修正版"), {
            "task_id": task_id,
            "file_path": file_path,
            "code": code,
            "notes": result.get("notes", ""),
            "retry_count": retry_count + 1,
            "developer": self.name,
        })


if __name__ == "__main__":
    import sys
    agent_name = sys.argv[1] if len(sys.argv) > 1 else "developer1"
    DeveloperAgent(agent_name).run()
