import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agents.base_agent import BaseAgent

SYSTEM_PROMPT = """あなたはAIソフトウェア開発会社のSoftware Architectです。
CEOから仕様書を受け取り、技術設計を行い、タスクを並列で開発者に割り当てます。

あなたの役割:
1. 仕様書を読み、技術スタックを選定する
2. ファイル構成・アーキテクチャを設計する
3. タスクを独立した単位に分解し、Developer1とDeveloper2に並列で割り当てる
4. 各タスクには依存関係を明示する
5. 設計ドキュメントを作成する

タスク分解のルール:
- 各タスクは1つのファイルまたは機能単位にする
- タスクIDは "T-001", "T-002" 形式
- assignee は "developer1" または "developer2" で交互に振り分ける
- 依存タスクが完了するまで後続タスクは送らない

レスポンス形式（JSONで返すこと）:
{
  "tech_stack": "使用技術の説明",
  "file_structure": "ファイル構成（テキスト）",
  "design_doc": "設計ドキュメント全文",
  "tasks": [
    {
      "task_id": "T-001",
      "assignee": "developer1",
      "title": "タスクタイトル",
      "description": "実装内容の詳細",
      "output_file": "src/main.py",
      "dependencies": [],
      "context": "実装時に参照すべき情報"
    }
  ]
}"""


class ArchitectAgent(BaseAgent):
    def __init__(self):
        super().__init__("architect")
        self.pending_tasks: list[dict] = []
        self.completed_tasks: set[str] = set()
        # ディスパッチ済み（=Developerに送ったが、まだ完了していない作業中）タスクID
        self.dispatched_tasks: set[str] = set()

    def process_inbox(self):
        messages = self.read_inbox()
        for msg in messages:
            self._handle_message(msg)

    def _handle_message(self, msg: dict):
        msg_type = msg.get("type")
        content = msg.get("content", "")
        sender = msg.get("from", "")

        self.log_event("message_received", f"← [{sender}] {msg_type}")
        self.update_state("agent_architect_status", "working")

        if msg_type == "design_request":
            self._handle_design_request(content, msg)
        elif msg_type == "task_done":
            self._handle_task_done(msg)
        elif msg_type == "revised_instruction":
            self._handle_revised_instruction(content, msg)

        self.update_state("agent_architect_status", "waiting")

    def _handle_design_request(self, spec: str, msg: dict):
        self.log_event("designing", "設計開始")
        self.completed_tasks = set()
        self.dispatched_tasks = set()

        result = self.call_claude(SYSTEM_PROMPT, [
            {"role": "user", "content": f"以下の仕様書に基づいて設計・タスク分解してください:\n\n{spec}"}
        ])

        try:
            start = result.find("{")
            end = result.rfind("}") + 1
            design = json.loads(result[start:end])
        except Exception:
            self.log_event("design_error", "設計JSONのパースに失敗")
            return

        # save design doc
        doc_path = self.output_dir / "docs" / "design.md"
        doc_path.write_text(
            f"# 設計ドキュメント\n\n## 技術スタック\n{design.get('tech_stack','')}\n\n"
            f"## ファイル構成\n```\n{design.get('file_structure','')}\n```\n\n"
            f"## 詳細設計\n{design.get('design_doc','')}",
            encoding="utf-8"
        )
        self.log_event("design_doc_created", "docs/design.md を作成")

        tasks = design.get("tasks", [])
        self.pending_tasks = tasks
        self.update_state("all_tasks", [t["task_id"] for t in tasks])
        self.update_state("completed_tasks", [])

        self._dispatch_ready_tasks()

    def _handle_task_done(self, msg: dict):
        task_id = msg.get("task_id")
        self.completed_tasks.add(task_id)
        # 完了したら「作業中」集合から外し、dispatched_tasks の意味論を実体に合わせる
        self.dispatched_tasks.discard(task_id)
        state = self.get_state()
        completed = state.get("completed_tasks", [])
        completed.append(task_id)
        self.update_state("completed_tasks", completed)
        self.log_event("task_done", f"{task_id} 完了")

        all_tasks = state.get("all_tasks", [])
        if set(all_tasks) <= self.completed_tasks:
            self.log_event("all_tasks_done", "全タスク完了 → CEOへ報告")
            self.send_message("ceo", "task_complete",
                f"全{len(all_tasks)}タスクの実装が完了しました。成果物は /output に格納されています。")
        else:
            self._dispatch_ready_tasks()

    def _handle_revised_instruction(self, content: str, msg: dict):
        task_id = msg.get("task_id")
        self.log_event("revised_instruction", f"タスク {task_id} を修正指示で再割り当て")
        # find the task and reassign
        # 修正再割り当ては _dispatch_ready_tasks を経由せず直接 send_message するため、
        # dispatched_tasks に入っていてもリトライ再送はブロックされない。
        # 再び作業中になるので dispatched_tasks に入れて状態の整合性を保つ。
        for task in self.pending_tasks:
            if task["task_id"] == task_id:
                task["description"] = content
                task["retry_count"] = 0
                self.send_message(task["assignee"], "assign_task", task["description"], {
                    "task_id": task["task_id"],
                    "output_file": task["output_file"],
                    "context": task.get("context", ""),
                    "retry_count": 0,
                })
                self.dispatched_tasks.add(task_id)
                break

    def _dispatch_ready_tasks(self):
        # 対応済み(重複ディスパッチ): self.dispatched_tasks で作業中タスクを追跡し、
        #   未完了かつ未ディスパッチかつ依存が全て完了のタスクのみ送信する。
        #   これにより T-001 完了で再呼び出しされても、作業中の T-002 は再送されない。
        for task in self.pending_tasks:
            task_id = task["task_id"]
            if task_id in self.completed_tasks or task_id in self.dispatched_tasks:
                continue
            deps = task.get("dependencies", [])
            if all(d in self.completed_tasks for d in deps):
                assignee = task["assignee"]
                self.log_event("task_assigned", f"{task_id} → {assignee}: {task['title']}")
                self.send_message(assignee, "assign_task", task["description"], {
                    "task_id": task_id,
                    "title": task["title"],
                    "output_file": task["output_file"],
                    "context": task.get("context", ""),
                    "retry_count": 0,
                })
                self.dispatched_tasks.add(task_id)


if __name__ == "__main__":
    ArchitectAgent().run()
