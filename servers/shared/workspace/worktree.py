import subprocess
import shutil
from pathlib import Path
from typing import Tuple

class WorktreeManager:
    """
    Manages physical isolation using Git Worktrees.
    Provides a real filesystem sandbox for autonomous agents.
    """
    def __init__(self, repo_root: str):
        self.repo_root = Path(repo_root).resolve()
        
        # Verify it's a valid git repository
        if not (self.repo_root / ".git").exists():
            raise ValueError(f"Not a valid git repository: {self.repo_root}")

    def _run_git(self, *args, cwd: Path = None) -> Tuple[bool, str, str]:
        """Runs a git command and returns (success, stdout, stderr)."""
        target_cwd = cwd or self.repo_root
        process = subprocess.run(
            ["git"] + list(args),
            cwd=target_cwd,
            capture_output=True,
            text=True
        )
        return process.returncode == 0, process.stdout, process.stderr

    def create(self, branch_name: str, base_ref: str = "HEAD") -> Path:
        """
        Creates a new worktree isolated from the main working directory.
        Creates the branch if it doesn't exist.
        """
        # A good practice is to put worktrees outside or in a dedicated ignored folder
        # to avoid polluting the main editor's view and search.
        worktrees_dir = self.repo_root / ".worktrees"
        worktrees_dir.mkdir(exist_ok=True)
        
        worktree_path = worktrees_dir / branch_name

        if worktree_path.exists():
            # If it exists, we might want to clean it or just reuse it. 
            # For strict isolation per task, we assume it shouldn't exist or we fail/clean.
            return worktree_path

        # Create the branch and the worktree in one go (git worktree add -b <branch> <path> <ref>)
        # If branch exists, we just check it out (git worktree add <path> <branch>)
        
        # Check if branch exists
        branch_exists, _, _ = self._run_git("rev-parse", "--verify", branch_name)
        
        if branch_exists:
            success, out, err = self._run_git("worktree", "add", str(worktree_path), branch_name)
        else:
            success, out, err = self._run_git("worktree", "add", "-b", branch_name, str(worktree_path), base_ref)

        if not success:
            raise RuntimeError(f"Failed to create worktree: {err}")

        return worktree_path

    def remove(self, branch_name: str, force: bool = False) -> bool:
        """
        Removes a worktree and its associated directory.
        """
        worktree_path = self.repo_root / ".worktrees" / branch_name
        if not worktree_path.exists():
            return False

        args = ["worktree", "remove"]
        if force:
            args.append("--force")
        args.append(str(worktree_path))

        success, out, err = self._run_git(*args)
        
        # Cleanup the directory if git didn't (sometimes happens with untracked files)
        if success and worktree_path.exists():
            shutil.rmtree(worktree_path, ignore_errors=True)
            
        return success
        
    def run_command(self, worktree_path: Path, command: str) -> Tuple[bool, str, str]:
        """
        Executes a shell command inside the isolated worktree.
        Crucial for running tests, linters, or builds safely.
        """
        if not worktree_path.exists():
             return False, "", "Worktree path does not exist."
             
        try:
            process = subprocess.run(
                command,
                shell=True, # Allows complex commands like 'npm run build && npm test'
                cwd=worktree_path,
                capture_output=True,
                text=True
            )
            return process.returncode == 0, process.stdout, process.stderr
        except Exception as e:
            return False, "", str(e)
