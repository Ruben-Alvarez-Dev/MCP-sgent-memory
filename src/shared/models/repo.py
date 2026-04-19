from typing import List

class RepoNode:
    def __init__(self, path: str, type: str = "file", signature: str = "", children: List['RepoNode'] = None):
        self.path = path
        self.type = type
        self.signature = signature
        self.children = children or []
