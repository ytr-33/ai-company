import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agents.base_agent import BaseAgent

MAX_RETRIES = 3

SYSTEM_PROMPT = """あなたはAIソフトウェア開発会社のSenior Code Reviewerです。
Developerが実装したコードをレビューし、品質を確保します。

レビュー観点:
1. 機能の正確性（要件を満たしているか）
2. エラーハンドリング（例外処理が適切か）
3. コードの可読性（命名・構造）
4. セキュリティ（SQLインジェクション・XSS等の脆弱性がないか）
5. パフォーマンス（明らかな問題がないか）
6. 型ヒント・ドキュメント

レスポンス形式（JSONで返すこと）:
{
  "verdict": "approved" | "rejected",
  "score": 1-10,
  "issues": ["問題点1", "問題点2"],
  "feedback": "開発者へのフィードバック（rejected の場合は具体的な修正指示）",
  "praise": "良かった点"
}"""


class ReviewerAgent(BaseAgent):
    def __init__(self):
        super().__init__("reviewer")

    def process_inbox(self):
        messages = self.read_inbox()
        for msg in messages:
            self._handle_message(msg)

    def _handle_message(self, msg: dict):
        msg_type = msg.get("type")
        sender = msg.get("from", "")

        self.log_event("message_received", f"← [{sender}] {msg_type}")
        self.update_state("agent_reviewer_status", "working")

        if msg_type == "review_request":
            self._handle_review(msg)

        self.update_state("agent_reviewer_status", "waiting")

    def _handle_review(self, msg: dict):
        task_id = msg.get("task_id", "T-???")
        file_path = msg.get("file_path", "")
        code = msg.get("code", "")
        notes = msg.get("notes", "")
        retry_count = msg.get("retry_count", 0)
        developer = msg.get("developer", "developer1")
        summary = msg.get("content", "")

        self.log_event("review_start", f"{task_id} ({file_path}) 試行{retry_count+1}回目")

        prompt = f"""以下のコードをレビューしてください。

タスクID: {task_id}
ファイル: {file_path}
開発者コメント: {summary}
実装上の注意点: {notes}

コード:
```
{code}
```"""

        result_text = self.call_claude(SYSTEM_PROMPT, [{"role": "user", "content": prompt}])

        try:
            start = result_text.find("{")
            end = result_text.rfind("}") + 1
            result = json.loads(result_text[start:end])
        except Exception:
            self.log_event("parse_error", "レビュー結果のパースに失敗")
            result = {"verdict": "approved", "score": 7, "issues": [], "feedback": "", "praise": ""}

        verdict = result.get("verdict", "approved")
        score = result.get("score", 0)
        self.log_event("review_done", f"{task_id}: {verdict} (スコア:{score}/10)")

        if verdict == "approved":
            self._approve(task_id, file_path, result)
            self.send_message("architect", "task_done", f"{task_id} が承認されました (スコア:{score}/10)", {
                "task_id": task_id,
                "file_path": file_path,
            })
        else:
            if retry_count >= MAX_RETRIES - 1:
                self._escalate(task_id, file_path, result, retry_count, developer)
            else:
                self._request_revision(task_id, file_path, code, result, retry_count, developer)

    def _approve(self, task_id: str, file_path: str, result: dict):
        self.log_event("approved", f"{task_id} 承認: {result.get('praise','')[:60]}")

    def _request_revision(self, task_id: str, file_path: str, code: str, result: dict, retry_count: int, developer: str):
        feedback = result.get("feedback", "")
        issues = result.get("issues", [])
        issue_text = "\n".join(f"- {i}" for i in issues)
        full_feedback = f"問題点:\n{issue_text}\n\n修正指示:\n{feedback}"

        self.log_event("revision_requested", f"{task_id} 差し戻し (試行{retry_count+1}/{MAX_RETRIES}): {feedback[:60]}")

        self.send_message(developer, "revision_request", full_feedback, {
            "task_id": task_id,
            "file_path": file_path,
            "original_code": code,
            "retry_count": retry_count + 1,
        })

    def _escalate(self, task_id: str, file_path: str, result: dict, retry_count: int, developer: str):
        feedback = result.get("feedback", "")
        issues = result.get("issues", [])
        issue_text = "\n".join(f"- {i}" for i in issues)

        escalation_content = (
            f"タスク {task_id} ({file_path}) が{retry_count+1}回試行しても解決できませんでした。\n\n"
            f"問題点:\n{issue_text}\n\n"
            f"最後のフィードバック:\n{feedback}"
        )

        self.log_event("escalating", f"{task_id} → CEOにエスカレーション")
        self.send_message("ceo", "escalation", escalation_content, {
            "task_id": task_id,
            "file_path": file_path,
            "retry_count": retry_count + 1,
        })


if __name__ == "__main__":
    ReviewerAgent().run()
