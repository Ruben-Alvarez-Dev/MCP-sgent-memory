"""Core test fixtures — no external services required."""
import sys
import os

# Ensure src/ is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
