"""Tests for workspace.worktree — git worktree management.

Covers: creation, command execution, removal, rejection of non-git dirs.
"""

from __future__ import annotations

import pytest

from workspace.worktree import WorktreeManager


def test_rejects_non_git_dir(tmp_path):
    with pytest.raises(ValueError, match="Not a valid git repository"):
        WorktreeManager(str(tmp_path))


def test_create_and_remove_worktree(temp_git_repo):
    manager = WorktreeManager(str(temp_git_repo))
    branch = "task/test-feature"

    # Create
    wt_path = manager.create(branch)
    assert wt_path.exists()

    # Verify git knows about it
    success, out, _ = manager._run_git("worktree", "list")
    assert success
    assert branch in out

    # Run command inside worktree
    success, _, _ = manager.run_command(wt_path, "echo 'hello' > test_file.txt")
    assert success
    assert (wt_path / "test_file.txt").read_text().strip() == "hello"

    # File should NOT exist in main repo
    assert not (temp_git_repo / "test_file.txt").exists()

    # Remove
    assert manager.remove(branch, force=True) is True
    assert not wt_path.exists()


def test_remove_nonexistent_branch_returns_false(temp_git_repo):
    manager = WorktreeManager(str(temp_git_repo))
    assert manager.remove("nonexistent-branch", force=True) is False
