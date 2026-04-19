import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from steering.stagnation import StagnationMonitor
from steering.state import TaskContext, AgentState

def test_stagnation_monitor_detects_no_edits():
    monitor = StagnationMonitor(max_consecutive_failures=3)
    
    # Turn 1: 0 edits -> Not stuck yet
    assert monitor.record_turn(files_edited=0) is False
    
    # Turn 2: 0 edits -> Not stuck yet
    assert monitor.record_turn(files_edited=0) is False
    
    # Turn 3: 0 edits -> STUCK! (Hits max_consecutive_failures)
    assert monitor.record_turn(files_edited=0) is True
    
    # Check intervention prompt
    prompt = monitor.get_intervention_prompt()
    assert "multiple turns talking or apologizing" in prompt

def test_stagnation_monitor_resets_on_edit():
    monitor = StagnationMonitor(max_consecutive_failures=3)
    monitor.record_turn(files_edited=0)
    monitor.record_turn(files_edited=0)
    
    # Turn 3: Edits a file -> Counter resets
    assert monitor.record_turn(files_edited=1) is False
    
    # Next turn with 0 edits should NOT trigger stagnation immediately
    assert monitor.record_turn(files_edited=0) is False

def test_stagnation_monitor_detects_error_loops():
    monitor = StagnationMonitor(max_consecutive_failures=3)
    
    err_msg = "SyntaxError: invalid syntax on line 42"
    
    # Turn 1: Error happens
    assert monitor.record_turn(files_edited=1, current_error=err_msg) is False
    
    # Turn 2: Same error happens
    assert monitor.record_turn(files_edited=1, current_error=err_msg) is False
    
    # Turn 3: Exact same error -> STUCK!
    assert monitor.record_turn(files_edited=1, current_error=err_msg) is True
    
    prompt = monitor.get_intervention_prompt()
    assert "stuck in an error loop" in prompt

def test_task_context_saves_and_loads(tmp_path: Path):
    ctx = TaskContext(tmp_path)
    ctx.task_description = "Fix the RAG pipeline"
    ctx.plan = ["Step 1", "Step 2"]
    
    # Change state and save
    ctx.transition(AgentState.CODING)
    
    # Create a new context instance pointing to the same path
    new_ctx = TaskContext(tmp_path)
    new_ctx.load_state()
    
    assert new_ctx.state == AgentState.CODING
    assert new_ctx.task_description == "Fix the RAG pipeline"
    assert new_ctx.plan == ["Step 1", "Step 2"]
    assert (tmp_path / "PLAN.md").exists()
