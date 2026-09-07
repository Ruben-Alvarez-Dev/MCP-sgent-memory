"""Path setup for the eval fixture package (mirrors tests/conftest.py)."""

import os
import sys

_HERE = os.path.dirname(__file__)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
