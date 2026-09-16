"""進捗ファイル。画面はこれを読んで表示する。"""

from __future__ import annotations

import json
from pathlib import Path


def write_status(out_dir: Path, step: str, message: str, pct: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    pct = min(100, max(0, pct))
    payload = {"step": step, "message": message, "pct": pct}
    (out_dir / "status.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"[{pct:3d}%] {step}: {message}", flush=True)
