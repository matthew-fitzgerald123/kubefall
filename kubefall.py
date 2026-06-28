#!/usr/bin/env python3
"""Thin entry point for kubefall.

Lets the game run straight from a checkout with `python kubefall.py`, without
needing to pip install the package first. It just puts src/ on the path and
hands off to the engine.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from kubefall.engine import main

if __name__ == "__main__":
    raise SystemExit(main())
