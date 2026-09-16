"""コマンドライン。`uv run retail-lab <command>` で使う。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path

from retail_lab import kaggle, registry, tracking
from retail_lab.competition import data_dir, output_dir, run_output_dir
from retail_lab.experiment import run_experiment
from retail_lab.status import write_status

REPO_ROOT = Path(__file__).resolve().parents[2]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="retail-lab", description="小売コンペの実験と取得")
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--competition", default=registry.DEFAULT_SLUG)
    sub = parser.add_subparsers(dest="command", required=True)

    run_cmd = sub.add_parser("run", help="実験を走らせて submission を作る")
    run_cmd.add_argument("--source", choices=["demo", "kaggle"], default="demo")
    run_cmd.add_argument("--out", type=Path, default=None)
    run_cmd.add_argument("--skip-foundation", action="store_true", help="基盤モデルを飛ばす")
    run_cmd.add_argument("--label", default="direct-foundation-v1", help="実験を識別する名前")
    run_cmd.add_argument(
        "--reuse-run",
        default=None,
        help="指定Runの Chronos / TimesFM 予測を再利用する（タグまたは Run ID）",
    )

    sub.add_parser("fetch", help="Kaggle から公式データを取得する")
    sub.add_parser("status", help="データの取得状況を見る")
    submit_cmd = sub.add_parser("submit", help="生成済みの submission.csv を Kaggle に提出する")
    submit_cmd.add_argument(
        "--message",
        default="Retail Lab submission",
        help="Kaggle の提出一覧に表示する説明",
    )
    sub.add_parser("preflight", help="提出できる状態か（権限と参加状態）を確かめる")
    runs_cmd = sub.add_parser("runs", help="実験Runとタグを見る")
    runs_cmd.add_argument("--json", action="store_true")
    promote_cmd = sub.add_parser("promote", help="Runまたはタグへロールバックする")
    promote_cmd.add_argument("ref")
    tag_cmd = sub.add_parser("tag", help="Runに人が読めるタグを付ける")
    tag_cmd.add_argument("tag")
    tag_cmd.add_argument("ref")
    score_cmd = sub.add_parser("leaderboard", help="公開LBスコアをRunに記録する")
    score_cmd.add_argument("ref")
    score_cmd.add_argument("score", type=float)
    sub.add_parser("list", help="登録済みのコンペを見る")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root: Path = args.root

    if args.command == "list":
        for spec in registry.specs():
            print(f"{spec.slug}\t{spec.title}")
        return 0

    spec = registry.spec(args.competition)

    out_root = output_dir(root, spec.slug)
    if args.command == "runs":
        payload = {"runs": tracking.list_runs(out_root), "tags": tracking.tags(out_root)}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if args.command == "promote":
        print(json.dumps(tracking.promote_run(out_root, args.ref), ensure_ascii=False, indent=2))
        return 0
    if args.command == "tag":
        tracking.tag_run(out_root, args.tag, tracking.resolve(out_root, args.ref))
        return 0
    if args.command == "leaderboard":
        print(
            json.dumps(
                tracking.set_leaderboard(out_root, args.ref, args.score),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "status":
        target = data_dir(root, spec.slug, "kaggle")
        state = kaggle.status(root, spec.kaggle_slug, target, list(spec.required_files))
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 0

    if args.command == "fetch":
        target = data_dir(root, spec.slug, "kaggle")
        try:
            result = kaggle.download(root, spec.kaggle_slug, target, list(spec.required_files))
        except kaggle.KaggleError as exc:
            print(
                json.dumps(
                    {"ok": False, "error": str(exc), "hint": exc.hint},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "preflight":
        out = output_dir(root, spec.slug)
        state = kaggle.check_submit_access(
            root=root,
            slug=spec.kaggle_slug,
            submission=out / "submission.csv",
        )
        state["file"] = kaggle.describe_submission(
            out / "submission.csv",
            data_dir(root, spec.slug, "kaggle") / "sample_submission.csv",
        )
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 0 if state["ok"] else 1

    if args.command == "submit":
        out = output_dir(root, spec.slug)
        result_path = out / "result.json"
        if not result_path.exists():
            print("結果がありません。先に公式データで予測してください。", file=sys.stderr)
            return 1
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if result.get("source") != "kaggle":
            print(
                "表示中の結果はデモデータ由来です。公式Kaggle CSVで予測してから提出してください。",
                file=sys.stderr,
            )
            return 1
        try:
            receipt = kaggle.submit(
                root=root,
                slug=spec.kaggle_slug,
                submission=out / "submission.csv",
                sample=data_dir(root, spec.slug, "kaggle") / "sample_submission.csv",
                message=args.message,
            )
        except kaggle.KaggleError as exc:
            print(
                json.dumps(
                    {"ok": False, "error": str(exc), "hint": exc.hint},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 1
        (out / "last_submission.json").write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
        return 0

    out = args.out or run_output_dir(root, spec.slug, args.source)
    reuse = None
    if getattr(args, "reuse_run", None):
        reuse_id = tracking.resolve(out_root, args.reuse_run)
        reuse = out_root / "runs" / reuse_id
    return _run(
        root,
        spec.slug,
        args.source,
        out,
        skip_foundation=args.skip_foundation,
        label=args.label,
        reuse_run=reuse,
    )


def _run(
    root: Path,
    slug: str,
    source: str,
    out: Path,
    skip_foundation: bool,
    label: str,
    reuse_run: Path | None = None,
) -> int:
    """実験を1本走らせる。画面はここが書くファイルだけを見る。"""
    out.mkdir(parents=True, exist_ok=True)
    error_path = out / "error.json"
    pid_path = out / "run.pid"
    error_path.unlink(missing_ok=True)
    pid_path.write_text(str(os.getpid()), encoding="utf-8")
    write_status(out, "load", "データを読み込みます", 5)
    try:
        prepared = registry.get(slug).prepare(root, source)
        result = run_experiment(prepared, out, skip_foundation=skip_foundation, reuse_run=reuse_run)
        run_id = tracking.new_run_id(label)
        result["run_id"] = run_id
        result["method_version"] = label
        (out / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        tracking.archive_run(out, run_id, label)
        tracking.consider_champion(out, run_id)
    except kaggle.KaggleError as exc:
        _fail(out, str(exc), exc.hint)
        return 1
    except Exception as exc:  # noqa: BLE001 - 画面に出すため必ず受ける
        _fail(out, f"{type(exc).__name__}: {exc}", "")
        traceback.print_exc()
        return 1
    finally:
        pid_path.unlink(missing_ok=True)
    return 0


def _fail(out: Path, message: str, hint: str) -> None:
    payload = {"message": message, "hint": hint}
    (out / "error.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    write_status(out, "failed", message, 100)
    print(f"{message} {hint}".strip(), file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
