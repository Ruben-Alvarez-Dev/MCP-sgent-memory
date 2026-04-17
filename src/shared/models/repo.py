"""Repository mapping models for hierarchical context retrieval."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


RepoNodeType = Literal["file", "class", "function", "module"]


class RepoNode(BaseModel):
    """A node inside the repository map."""

    path: str
    type: RepoNodeType
    signature: str
    dependencies: list[str] = Field(default_factory=list)
    children: list["RepoNode"] = Field(default_factory=list)


class RepoMap(BaseModel):
    """Hierarchical summary for a requested repository target."""

    root: RepoNode
    immediate_dependencies: list[RepoNode] = Field(default_factory=list)
    summary: str = ""
