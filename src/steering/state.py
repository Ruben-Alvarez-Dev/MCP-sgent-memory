import enum
from pathlib import Path
import json
from typing import Dict, Any

class AgentState(enum.Enum):
    PLANNING = "PLANNING"
    CODING = "CODING"
    VERIFICATION = "VERIFICATION"
    DONE = "DONE"
    FAILED = "FAILED"

class TaskContext:
    """
    Holds the state of the current task. Backed by PROGRESS.md or PLAN.md files.
    """
    def __init__(self, worktree_path: Path):
        self.worktree_path = worktree_path
        self.state = AgentState.PLANNING
        self.plan = []
        self.progress = ""
        self.task_description = ""

    def save_state(self):
        """Persists the state to the worktree to survive agent restarts."""
        state_data = {
            "state": self.state.value,
            "plan": self.plan,
            "progress": self.progress,
            "task": self.task_description
        }
        (self.worktree_path / ".ralph_state.json").write_text(json.dumps(state_data))
        
        # Also write human-readable artifacts if needed
        if self.plan:
             (self.worktree_path / "PLAN.md").write_text("\\n".join([str(p) for p in self.plan]))
        if self.progress:
             (self.worktree_path / "PROGRESS.md").write_text(self.progress)

    def load_state(self):
        """Restores state if it exists."""
        state_file = self.worktree_path / ".ralph_state.json"
        if state_file.exists():
            data = json.loads(state_file.read_text())
            self.state = AgentState(data.get("state", "PLANNING"))
            self.plan = data.get("plan", [])
            self.progress = data.get("progress", "")
            self.task_description = data.get("task", "")

    def transition(self, to_state: AgentState):
        """Moves to a new state and logs it."""
        self.state = to_state
        self.save_state()
