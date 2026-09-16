## 変更内容

-

## 実験への影響

- [ ] 予測手法を変更した
- [ ] ローカルRMSLEを記録した
- [ ] 悪化した結果と原因仮説も記録した
- [ ] Runタグ／ロールバックへの影響を確認した

## 確認

- [ ] `uv run pytest tests/unit`
- [ ] `uv run pytest tests/integration`
- [ ] `uv run ruff check .`
- [ ] `uv run ruff format --check .`
- [ ] `uv run mypy src`
- [ ] `npm run lint`
- [ ] `npm run build`
