"""コマンドライン。`uv run retail-lab <command>` で使う。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from retail_lab import kaggle, registry
from retail_lab.competition import data_dir, output_dir
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

    sub.add_parser("fetch", help="Kaggle から公式データを取得する")
    sub.add_parser("status", help="データの取得状況を見る")
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

    out = args.out or output_dir(root, spec.slug)
    out.mkdir(parents=True, exist_ok=True)
    write_status(out, "load", "データを読み込みます", 5)
    module = registry.get(spec.slug)
    try:
        prepared = module.prepare(root, args.source)
    except kaggle.KaggleError as exc:
        message = f"{exc} {exc.hint}".strip()
        print(message, file=sys.stderr)
        return 1
    run_experiment(prepared, out, skip_foundation=args.skip_foundation)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
