#!/usr/bin/env python3
"""Standalone runner for BITWILL."""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bitwill.cli.interface import main

if __name__ == '__main__':
    main()
