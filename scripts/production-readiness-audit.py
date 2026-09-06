#!/usr/bin/env python3
"""Entry point for the read-only production readiness audit.

Usage:
    python scripts/production-readiness-audit.py
    python scripts/production-readiness-audit.py --json
    python scripts/production-readiness-audit.py --debug

Exit code 0 = READY, 1 = HOLD. See scripts/production_readiness/README.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.production_readiness.main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
