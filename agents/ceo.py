import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agents.base_agent import BaseAgent

SYSTEM_PROMPT = """あなたはAIソフトウェア開発会社のCEOです。
ユーザーからソフトウェア開発の依頼を受け、要件を明確化し、Architectに設計を依頼します。

あなたの役割:
1. ユーザーからの依頼を受け取る
2. 不明点があれば質問リストを作成し、ユーザーに確認する
3. 要件が明確になったら詳細な仕様書を作成し、Architectに渡す
4. 開発中の問題（エスカレーション）に対応する
5. 完成報告をユーザーに伝える

レスポンス形式（JSONで返すこと）:
{
  "action": "ask_user" | "delegate_to_architect" | "respond_to_escalation" | "notify_completion",
  "questions": ["質問1", "質問2"],  // action=ask_user の場合
  "spec": "詳細仕様書テキスト",     // action=delegate_to_architect の場合
  "response": "対応内容",           // action=respond_to_escalation の場合
  "summary": "完了サマリー"         // action=notify_completion の場合
}"""


class CEOAgent(BaseAgent):
    def __init__(self):
        super().__init__("ceo")
        self.conversation_history = []

    def process_inbox(self):
        messages = self.read_inbox()
        for msg in messages:
            self._handle_message(msg)

    def _handle_message(self, msg: dict):
        msg_type = msg.get("type")
        content = msg.get("content", "")
        sender = msg.get("from", "user")

        self.log_event("message_received", f"← [{sender}] {msg_type}: {content[:80]}")
        self.update_state("agent_ceo_status", "working")

        if msg_type == "user_task":
            self._handle_user_task(content, msg)
        elif msg_type == "user_answer":
            self._handle_user_answer(content, msg)
        elif msg_type == "escalation":
            self._handle_escalation(content, msg)
        elif msg_type == "task_complete":
            self._handle_completion(content, msg)

        self.update_state("agent_ceo_status", "waiting")

    def _handle_user_task(self, task: str, msg: dict):
        self.conversation_history = [{"role": "user", "content": f"依頼: {task}"}]
        self.log_event("task_received", f"新規タスク: {task}")
        self.update_state("current_task", task)

        result = self._think()
        self._execute_action(result, msg)

    def _handle_user_answer(self, answer: str, msg: dict):
        self.conversation_history.append({"role": "user", "content": f"回答: {answer}"})
        self.log_event("user_answered", answer[:80])

        result = self._think()
        self._execute_action(result, msg)

    def _handle_escalation(self, content: str, msg: dict):
        task_id = msg.get("task_id", "不明")
        retry_count = msg.get("retry_count", 3)
        self.log_event("escalation_received", f"タスク {task_id} がエスカレーション (試行{retry_count}回)")

        escalation_context = f"""
エスカレーション通知:
タスクID: {task_id}
問題内容: {content}
試行回数: {retry_count}回

この問題を解決するための指示を出してください。
アーキテクチャを変更すべきか、アプローチを変えるべきか検討してください。
"""
        self.conversation_history.append({"role": "user", "content": escalation_context})
        result = self._think()
        self._execute_action(result, msg)

    def _handle_completion(self, content: str, msg: dict):
        self.log_event("project_complete", content[:120])
        self.update_state("project_status", "completed")

        # notify user via user_response file
        user_msg = {
            "type": "completion",
            "content": content,
            "summary": f"プロジェクト完了: {content}",
        }
        response_path = self.state_dir / "user_response.json"
        response_path.write_text(json.dumps(user_msg, ensure_ascii=False, indent=2))
        print(f"\n✅ [CEO] プロジェクト完了:\n{content}\n")

    def _think(self) -> dict:
        text = self.call_claude(SYSTEM_PROMPT, self.conversation_history)
        # extract JSON from response
        try:
            # try to find JSON block
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(text[start:end])
        except Exception:
            pass
        return {"action": "ask_user", "questions": ["要件をもう少し詳しく教えてください。"]}

    def _execute_action(self, result: dict, original_msg: dict):
        action = result.get("action")
        self.conversation_history.append({"role": "assistant", "content": json.dumps(result, ensure_ascii=False)})

        if action == "ask_user":
            questions = result.get("questions", [])
            question_text = "\n".join(f"  {i+1}. {q}" for i, q in enumerate(questions))
            user_question = {
                "type": "ceo_question",
                "content": question_text,
            }
            response_path = self.state_dir / "user_response.json"
            response_path.write_text(json.dumps(user_question, ensure_ascii=False, indent=2))
            self.log_event("asking_user", f"{len(questions)}個の質問を送信")
            print(f"\n[CEO] 確認事項:\n{question_text}\n")

        elif action == "delegate_to_architect":
            spec = result.get("spec", "")
            self.log_event("delegating_to_architect", "仕様書をArchitectへ送信")
            self.update_state("spec", spec)
            self.send_message("architect", "design_request", spec, {
                "original_task": self.get_state().get("current_task", ""),
            })

        elif action == "respond_to_escalation":
            response = result.get("response", "")
            self.log_event("escalation_resolved", response[:80])
            task_id = original_msg.get("task_id")
            # resend to architect with revised instructions
            self.send_message("architect", "revised_instruction", response, {
                "task_id": task_id,
            })

        elif action == "notify_completion":
            summary = result.get("summary", "プロジェクト完了")
            user_msg = {"type": "completion", "content": summary}
            response_path = self.state_dir / "user_response.json"
            response_path.write_text(json.dumps(user_msg, ensure_ascii=False, indent=2))
            print(f"\n✅ [CEO] {summary}\n")


if __name__ == "__main__":
    CEOAgent().run()
