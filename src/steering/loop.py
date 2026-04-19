import asyncio
import json
from pathlib import Path
from workspace.worktree import WorktreeManager
from steering.state import TaskContext, AgentState
from steering.stagnation import StagnationMonitor
from typing import Callable, Coroutine, Tuple

class RalphLoop:
    """
    The orchestrator. Forces an LLM agent to follow a task until completion
    or explicit failure. Uses Git Worktrees for isolation and RAG for context.
    """
    def __init__(self, repo_root: str, task_name: str, agent_fn: Callable[[str, list], Coroutine[None, None, Tuple[str, int]]]):
        self.workspace = WorktreeManager(repo_root)
        self.task_name = task_name
        self.agent_fn = agent_fn # The LLM abstraction (takes context, history, returns response, files_edited)
        self.stagnation = StagnationMonitor()
        self.conversation_history = []
        self.worktree_path = None
        self.ctx = None

    async def start(self, task_description: str):
        """Initializes the loop and the environment."""
        print(f"INFO: Starting Ralph Loop for task '{self.task_name}'")
        self.worktree_path = self.workspace.create(branch_name=f"ralph/{self.task_name}")
        self.ctx = TaskContext(self.worktree_path)
        self.ctx.task_description = task_description
        self.ctx.save_state()
        
        # Here we would normally trigger index_repo to generate Code Maps for the new worktree
        
        await self._run_state_machine()

    async def _run_state_machine(self):
        """The core loop."""
        while self.ctx.state not in (AgentState.DONE, AgentState.FAILED):
            if self.ctx.state == AgentState.PLANNING:
                await self._phase_planning()
            elif self.ctx.state == AgentState.CODING:
                await self._phase_coding()
            elif self.ctx.state == AgentState.VERIFICATION:
                await self._phase_verification()
                
    async def _phase_planning(self):
        """Forces the agent to output a PLAN.md before coding."""
        prompt = f"TASK: {self.ctx.task_description}\\nYou are in PLANNING phase. Analyze the task and write a plan to PLAN.md. Use the write tool."
        
        response, files_edited = await self.agent_fn(prompt, self.conversation_history)
        self.conversation_history.append({"role": "assistant", "content": response})
        
        if (self.worktree_path / "PLAN.md").exists():
            print("INFO: PLAN.md generated. Advancing to CODING.")
            self.ctx.transition(AgentState.CODING)
            self.stagnation.reset()
        else:
            print("WARNING: Agent failed to produce PLAN.md.")
            self.conversation_history.append({"role": "system", "content": "You must create PLAN.md before advancing."})

    async def _phase_coding(self):
        """The main loop. Agent edits files. Stagnation is monitored."""
        # Inject context from vk-cache (RAG) here based on the task
        prompt = "You are in CODING phase. Implement the plan. Output 'DONE CODING' when finished."
        
        response, files_edited = await self.agent_fn(prompt, self.conversation_history)
        self.conversation_history.append({"role": "assistant", "content": response})

        # Check for stagnation (talking without acting)
        if self.stagnation.record_turn(files_edited):
            intervention = self.stagnation.get_intervention_prompt()
            print(f"CRITICAL: Stagnation detected! Injecting intervention: {intervention[:50]}...")
            
            # Reset context window to clear confusion
            self.conversation_history = self.conversation_history[-2:] # Keep only recent turns
            self.conversation_history.append({"role": "system", "content": intervention})
            self.stagnation.reset() # Give them another chance
            return # Skip the rest of this turn

        if "DONE CODING" in response:
            print("INFO: Agent signaled completion. Advancing to VERIFICATION.")
            self.ctx.transition(AgentState.VERIFICATION)
            self.stagnation.reset()

    async def _phase_verification(self):
        """Runs tests. If they fail, sends error back to agent in CODING phase."""
        print("INFO: Running verification suite...")
        # Placeholder for a real test command configured for the project
        success, out, err = self.workspace.run_command(self.worktree_path, "pytest")
        
        if success:
            print("SUCCESS: Tests passed! Task is DONE.")
            self.ctx.transition(AgentState.DONE)
            # Here we would trigger AutoDream to mine the successful diffs
            # and optionally use workspace.run_git("merge") or create a PR.
        else:
            print("ERROR: Tests failed. Sending agent back to CODING.")
            error_msg = f"Tests failed. Fix the following errors:\\n\\n{out}\\n{err}"
            
            # Check stagnation on the exact same error
            if self.stagnation.record_turn(1, current_error=err):
                intervention = self.stagnation.get_intervention_prompt()
                print(f"CRITICAL: Error Loop detected! {intervention[:50]}...")
                error_msg = f"{intervention}\\n\\n{error_msg}"
                self.conversation_history = self.conversation_history[-2:]

            self.conversation_history.append({"role": "system", "content": error_msg})
            self.ctx.transition(AgentState.CODING)

    def cleanup(self):
        """Tears down the isolation environment."""
        if self.worktree_path:
             self.workspace.remove(f"ralph/{self.task_name}", force=True)
             print(f"INFO: Worktree ralph/{self.task_name} removed.")
