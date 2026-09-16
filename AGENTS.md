<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

# Project Instructions

## Environment

- Python 3.12を使用する
- 依存関係の管理にはuvを使用する
- pip installは使用しない
- 仮想環境を手動で作成しない
- Pythonコマンドは `uv run` 経由で実行する

## Commands

- Install: `uv sync --frozen`
- Test: `uv run pytest`
- Lint: `uv run ruff check .`
- Format check: `uv run ruff format --check .`
- Type check: `uv run mypy src`

## Coding rules

- 型ヒントを付ける
- 新しい依存関係を追加する前に確認する
- 既存のAPI仕様を変更しない
- テストを追加してから実装を完了する
- `uv.lock`を更新した場合は変更内容を説明する

## Completion criteria

作業完了前に以下を実行する。

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```
