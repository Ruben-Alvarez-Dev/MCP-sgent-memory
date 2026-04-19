import sys
import subprocess
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from workspace.worktree import WorktreeManager

@pytest.fixture
def mock_git_repo(tmp_path: Path):
    """Creates a real (but temporary) git repository for testing WorktreeManager."""
    repo_dir = tmp_path / "mock_repo"
    repo_dir.mkdir()
    
    # Initialize a dummy git repo
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    
    # Must have at least one commit to create a branch/worktree from HEAD
    (repo_dir / "initial.txt").write_text("Init")
    subprocess.run(["git", "add", "initial.txt"], cwd=repo_dir, check=True, capture_output=True)
    # Using generic author for the test commit to avoid git config requirement failures
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "Initial commit"],
        cwd=repo_dir, check=True, capture_output=True
    )
    
    return repo_dir

def test_worktree_manager_rejects_non_git_dir(tmp_path: Path):
    with pytest.raises(ValueError, match="Not a valid git repository"):
        WorktreeManager(str(tmp_path))

def test_worktree_creation_and_removal(mock_git_repo: Path):
    manager = WorktreeManager(str(mock_git_repo))
    branch_name = "task/test-feature"
    
    # 1. Create worktree
    wt_path = manager.create(branch_name)
    assert wt_path.exists()
    assert (wt_path / ".git").exists() # Inside a worktree, .git is a file pointing to the main repo
    
    # Verify git knows about it
    success, out, err = manager._run_git("worktree", "list")
    assert success
    assert branch_name in out
    
    # 2. Run command inside worktree
    # Let's create a file using a shell command inside the worktree
    success, out, err = manager.run_command(wt_path, "echo 'hello' > test_file.txt")
    assert success
    assert (wt_path / "test_file.txt").read_text().strip() == "hello"
    
    # The file should NOT exist in the main repo root
    assert not (mock_git_repo / "test_file.txt").exists()
    
    # 3. Remove worktree
    removed = manager.remove(branch_name, force=True)
    assert removed is True
    assert not wt_path.exists()
    
    success, out, err = manager._run_git("worktree", "list")
    assert branch_name not in out
