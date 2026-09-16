"""Kaggle のデータ取得。コンペ slug を渡すだけで使い回せる。"""

from __future__ import annotations

import base64
import json
import os
import shutil
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

TOKEN_PREFIX = "KGAT_"
TOKEN_URL = "https://www.kaggle.com/settings"


class KaggleError(RuntimeError):
    """利用者に見せる想定のメッセージを持つ例外。"""

    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.hint = hint


def rules_url(slug: str) -> str:
    return f"https://www.kaggle.com/competitions/{slug}/rules"


def _download_url(slug: str) -> str:
    return f"https://www.kaggle.com/api/v1/competitions/data/download-all/{slug}"


def auth_header(root: Path) -> dict[str, str] | None:
    """Kaggle の2方式に対応する。

    - API トークン（``KGAT_`` で始まる）: Bearer 認証。ユーザー名は不要。
    - 旧来の username + key: Basic 認証。
    """
    token = os.environ.get("KAGGLE_API_TOKEN") or ""
    user = os.environ.get("KAGGLE_USERNAME") or ""
    key = os.environ.get("KAGGLE_KEY") or ""

    if not token and not key:
        for candidate in (root / "kaggle.json", Path.home() / ".kaggle" / "kaggle.json"):
            if not candidate.exists():
                continue
            try:
                blob = json.loads(candidate.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise KaggleError(
                    f"{candidate} が JSON として読めません。",
                    "Kaggle からダウンロードした kaggle.json をそのまま置いてください。",
                ) from exc
            token = token or str(blob.get("token") or blob.get("api_token") or "")
            user = user or str(blob.get("username") or "")
            key = key or str(blob.get("key") or "")
            break

    if token.startswith(TOKEN_PREFIX):
        return {"Authorization": f"Bearer {token}"}
    if key.startswith(TOKEN_PREFIX):
        return {"Authorization": f"Bearer {key}"}
    if user and key:
        basic = base64.b64encode(f"{user}:{key}".encode()).decode()
        return {"Authorization": f"Basic {basic}"}
    return None


def missing_files(target: Path, required: list[str]) -> list[str]:
    return [name for name in required if not (target / name).exists()]


def status(root: Path, slug: str, target: Path, required: list[str]) -> dict[str, object]:
    missing = missing_files(target, required)
    try:
        header = auth_header(root)
        credential_error = ""
    except KaggleError as exc:
        header = None
        credential_error = str(exc)
    return {
        "competition": slug,
        "ready": not missing,
        "missing": missing,
        "has_credentials": header is not None,
        "credential_error": credential_error,
        "rules_url": rules_url(slug),
        "token_url": TOKEN_URL,
    }


def download(root: Path, slug: str, target: Path, required: list[str]) -> dict[str, object]:
    """コンペのデータを取得して ``target`` に展開する。"""
    header = auth_header(root)
    if header is None:
        raise KaggleError(
            "Kaggle の認証情報がありません。",
            "Kaggle の Settings で API トークンを作り、KAGGLE_API_TOKEN を設定してください。"
            "旧来の方式なら KAGGLE_USERNAME と KAGGLE_KEY、または kaggle.json を置いてください。",
        )
    request = urllib.request.Request(
        _download_url(slug),
        headers={**header, "User-Agent": "retail-lab"},
    )
    archive_path = Path(tempfile.gettempdir()) / f"{slug}.zip"
    try:
        with (
            urllib.request.urlopen(request, timeout=900) as response,
            archive_path.open("wb") as dst,
        ):
            shutil.copyfileobj(response, dst)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise KaggleError(
                "Kaggle が認証またはアクセスを拒否しました。",
                "トークンが有効かを確かめ、コンペのページで規約に同意してください"
                "（Join Competition）。",
            ) from exc
        raise KaggleError(f"Kaggle への接続が失敗しました（HTTP {exc.code}）。") from exc
    except urllib.error.URLError as exc:
        raise KaggleError(f"Kaggle に接続できません: {exc.reason}") from exc

    target.mkdir(parents=True, exist_ok=True)
    wanted = set(required) | {"sample_submission.csv"}
    try:
        with zipfile.ZipFile(archive_path) as archive:
            for name in archive.namelist():
                base = Path(name).name
                if base in wanted:
                    with archive.open(name) as src, (target / base).open("wb") as dst:
                        dst.write(src.read())
    except zipfile.BadZipFile as exc:
        raise KaggleError(
            "受け取ったファイルが zip ではありませんでした。",
            "コンペの規約に同意していない場合、Kaggle は HTML を返します。",
        ) from exc

    missing = missing_files(target, required)
    if missing:
        raise KaggleError(f"取得できたが不足しています: {', '.join(missing)}")
    return {
        "ok": True,
        "dir": str(target),
        "sizes": {name: (target / name).stat().st_size for name in required},
    }
