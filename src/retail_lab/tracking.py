"""不変の実験Run、タグ、Championへの昇格とロールバック。

`outputs/<slug>/runs/<run-id>/` は一度作ったら変更しない。
人が使う名前（champion / previous-champion / 任意タグ）だけを別ファイルで付け替える。
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd

JsonDict = dict[str, Any]
ARTIFACTS = ("result.json", "submission.csv")
PRED_DIR = "preds"


def new_run_id(label: str = "run") -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    safe = "".join(c if c.isalnum() or c == "-" else "-" for c in label.lower()).strip("-")
    return f"{stamp}-{safe or 'run'}-{uuid.uuid4().hex[:6]}"


def write_preds(
    out: Path, val_preds: dict[str, pd.DataFrame], test_preds: dict[str, pd.DataFrame]
) -> None:
    dest = out / PRED_DIR
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for name, frame in val_preds.items():
        frame.to_parquet(dest / f"{name}_val.parquet", index=False)
    for name, frame in test_preds.items():
        frame.to_parquet(dest / f"{name}_test.parquet", index=False)


def load_cached_preds(run_dir: Path, model_id: str) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    import pandas as pd

    val = run_dir / PRED_DIR / f"{model_id}_val.parquet"
    test = run_dir / PRED_DIR / f"{model_id}_test.parquet"
    if not val.exists() or not test.exists():
        return None
    return pd.read_parquet(val), pd.read_parquet(test)


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _blend_row(result: JsonDict) -> JsonDict:
    for model in result.get("models", []):
        if model.get("id") == "blend":
            return model
    raise ValueError("result.json に提出候補の RMSLE がありません")


def _score(result: JsonDict) -> float:
    return float(_blend_row(result)["rmsle"])


def _holdout(result: JsonDict) -> float | None:
    value = _blend_row(result).get("holdout_rmsle")
    return float(value) if value is not None else None


def comparable_score(record: JsonDict) -> float:
    """Run同士を比べる点数。

    混合の重みを当てはめた行で測った点数は、グループ別の重みほど良く見える。
    そこで、隠して採点した点数があるRunはそれを使う。両方にあるときだけ比べる。
    """
    holdout = record.get("holdout_rmsle")
    if holdout is not None:
        return float(holdout)
    return float(record["local_rmsle"])


def archive_run(out: Path, run_id: str, label: str) -> JsonDict:
    """現在の成果物を新しい不変Runとして保存する。既存Runは上書きしない。"""
    run_dir = out / "runs" / run_id
    if run_dir.exists():
        raise FileExistsError(f"Run は既に存在します: {run_id}")
    for name in ARTIFACTS:
        if not (out / name).exists():
            raise FileNotFoundError(f"成果物がありません: {name}")

    result: JsonDict = _read_json(out / "result.json", {})
    record: JsonDict = {
        "run_id": run_id,
        "label": label,
        "created_at": datetime.now(UTC).isoformat(),
        "local_rmsle": _score(result),
        "holdout_rmsle": _holdout(result),
        "leaderboard": None,
        "source": result.get("source"),
        "method_version": result.get("method_version", label),
        "models": [
            {
                "id": model.get("id"),
                "rmsle": model.get("rmsle"),
                "weight": model.get("weight", 0),
            }
            for model in result.get("models", [])
            if model.get("status") == "ok"
        ],
    }

    temporary = out / "runs" / f".{run_id}.{uuid.uuid4().hex[:6]}"
    temporary.mkdir(parents=True)
    try:
        for name in ARTIFACTS:
            shutil.copy2(out / name, temporary / name)
        preds = out / PRED_DIR
        if preds.exists():
            shutil.copytree(preds, temporary / PRED_DIR)
        _atomic_json(temporary / "run.json", record)
        temporary.rename(run_dir)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    return record


def list_runs(out: Path) -> list[JsonDict]:
    runs_dir = out / "runs"
    if not runs_dir.exists():
        return []
    records = [_read_json(path / "run.json", {}) for path in runs_dir.iterdir() if path.is_dir()]
    return sorted(
        (record for record in records if record), key=lambda r: r["created_at"], reverse=True
    )


def tags(out: Path) -> dict[str, str]:
    tags: dict[str, str] = _read_json(out / "tags.json", {})
    return tags


def tag_run(out: Path, tag: str, run_id: str) -> None:
    if not (out / "runs" / run_id / "run.json").exists():
        raise KeyError(f"Run がありません: {run_id}")
    tag_map = tags(out)
    tag_map[tag] = run_id
    _atomic_json(out / "tags.json", tag_map)


def resolve(out: Path, ref: str) -> str:
    if (out / "runs" / ref / "run.json").exists():
        return ref
    try:
        return tags(out)[ref]
    except KeyError:
        raise KeyError(f"Run またはタグがありません: {ref}") from None


def promote_run(out: Path, ref: str) -> JsonDict:
    """Run/タグの成果物を現在値に戻す。Run自体は変更しない。"""
    run_id = resolve(out, ref)
    run_dir = out / "runs" / run_id
    for name in ARTIFACTS:
        temporary = out / f".{name}.{uuid.uuid4().hex[:6]}"
        shutil.copy2(run_dir / name, temporary)
        os.replace(temporary, out / name)
    src = run_dir / PRED_DIR
    dest = out / PRED_DIR
    if src.exists():
        temporary = out / f".{PRED_DIR}.{uuid.uuid4().hex[:6]}"
        shutil.copytree(src, temporary)
        if dest.exists():
            shutil.rmtree(dest)
        os.replace(temporary, dest)
    elif dest.exists():
        shutil.rmtree(dest)
    tag_run(out, "champion", run_id)
    return _read_json(run_dir / "run.json", {})


def champion(out: Path) -> JsonDict | None:
    run_id = tags(out).get("champion")
    if not run_id:
        return None
    return _read_json(out / "runs" / run_id / "run.json", None)


def consider_champion(out: Path, run_id: str) -> bool:
    """ローカル検証が改善したRunだけをChampionへ昇格する。"""
    candidate: JsonDict = _read_json(out / "runs" / run_id / "run.json", {})
    current = champion(out)
    if current is None or comparable_score(candidate) < comparable_score(current):
        if current is not None:
            tag_run(out, "previous-champion", current["run_id"])
        promote_run(out, run_id)
        tag_run(out, "latest", run_id)
        return True

    tag_run(out, "latest", run_id)
    # 実験中にトップレベルへ書かれた悪い成果物をChampionに戻す
    promote_run(out, current["run_id"])
    return False


def set_holdout(out: Path, run_id: str, score: float) -> JsonDict:
    """隠して採点した点数を、既存Runへ後から入れる。比較の物差しを揃えるため。"""
    path = out / "runs" / run_id / "run.json"
    record: JsonDict = _read_json(path, {})
    if not record:
        raise KeyError(f"Run がありません: {run_id}")
    record["holdout_rmsle"] = float(score)
    _atomic_json(path, record)
    return record


def set_leaderboard(out: Path, ref: str, score: float) -> JsonDict:
    run_id = resolve(out, ref)
    path = out / "runs" / run_id / "run.json"
    record: JsonDict = _read_json(path, {})
    record["leaderboard"] = float(score)
    _atomic_json(path, record)
    return record
