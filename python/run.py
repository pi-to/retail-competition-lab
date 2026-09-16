#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from engine import run  # noqa: E402

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Store Sales 予測")
    parser.add_argument("--source", choices=["demo", "kaggle"], default="demo")
    parser.add_argument("--root", type=Path, default=HERE.parent)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--skip-foundation", action="store_true")
    args = parser.parse_args()
    out = args.out or (args.root / "outputs")
    run(args.root, args.source, out, skip_foundation=args.skip_foundation)
