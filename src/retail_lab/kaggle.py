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
from typing import Any

import pandas as pd

TOKEN_PREFIX = "KGAT_"
TOKEN_URL = "https://www.kaggle.com/settings"


class KaggleError(RuntimeError):
    """利用者に見せる想定のメッセージを持つ例外。"""

    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.hint = hint


class SubmissionValidationError(KaggleError):
    """Kaggle に送る前のローカル検証で見つかった不整合。"""


def rules_url(slug: str) -> str:
    return f"https://www.kaggle.com/competitions/{slug}/rules"


def _download_url(slug: str) -> str:
    return f"https://www.kaggle.com/api/v1/competitions/data/download-all/{slug}"


def _submission_url() -> str:
    return "https://www.kaggle.com/api/v1/competitions/submission-url"


def _submit_url(slug: str) -> str:
    return f"https://www.kaggle.com/api/v1/competitions/submissions/submit/{slug}"


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


def validate_submission(submission: Path, sample: Path) -> dict[str, int | float]:
    """提出CSVが公式 sample_submission と同じ行を持つか検査する。

    ID の抜け・重複・余計な行、欠損、負の売上を送信前に止める。
    """
    if not submission.exists():
        raise SubmissionValidationError(
            "submission.csv がありません。先に公式データで予測してください。"
        )
    if not sample.exists():
        raise SubmissionValidationError("公式 sample_submission.csv がありません。")

    actual = pd.read_csv(submission)
    expected = pd.read_csv(sample)
    required = ["id", "sales"]
    if list(actual.columns) != required:
        raise SubmissionValidationError("提出CSVの列は id,sales の順である必要があります。")
    if "id" not in expected.columns:
        raise SubmissionValidationError("公式 sample_submission.csv に id 列がありません。")
    if len(actual) != len(expected):
        raise SubmissionValidationError(
            f"提出CSVの行数が違います（提出 {len(actual):,} / 公式 {len(expected):,}）。"
        )
    if actual["id"].duplicated().any():
        raise SubmissionValidationError("提出CSVの id が重複しています。")
    if set(actual["id"]) != set(expected["id"]):
        raise SubmissionValidationError(
            "提出CSVの id が公式 sample_submission.csv と一致しません。"
        )
    if actual["sales"].isna().any():
        raise SubmissionValidationError("提出CSVの sales に欠損があります。")
    if not pd.api.types.is_numeric_dtype(actual["sales"]):
        raise SubmissionValidationError("提出CSVの sales は数値である必要があります。")
    if (actual["sales"] < 0).any():
        raise SubmissionValidationError("提出CSVの sales に負の値があります。")

    return {
        "rows": int(len(actual)),
        "id_min": int(actual["id"].min()),
        "id_max": int(actual["id"].max()),
        "sales_min": float(actual["sales"].min()),
        "sales_max": float(actual["sales"].max()),
    }


def _json_request(
    url: str,
    headers: dict[str, str],
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            **headers,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "retail-lab",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise KaggleError(
            f"Kaggle API が提出を拒否しました（HTTP {exc.code}）。",
            _api_error_hint(exc.code, detail),
        ) from exc
    try:
        parsed: dict[str, Any] = json.loads(raw)
        return parsed
    except json.JSONDecodeError as exc:
        raise KaggleError("Kaggle API の応答を読み取れませんでした。") from exc


def _api_error_hint(code: int, detail: str) -> str:
    if code in (401, 403):
        return "APIトークン、コンペ規約への同意、または提出権限を確認してください。"
    if code == 429:
        return "提出回数の上限に達した可能性があります。Kaggle の提出一覧を確認してください。"
    try:
        payload = json.loads(detail)
        message = payload.get("message") or payload.get("error")
        if message:
            return str(message)
    except json.JSONDecodeError:
        pass
    return detail[:500]


def _multipart(fields: dict[str, str]) -> tuple[bytes, str]:
    boundary = f"----retail-lab-{os.urandom(12).hex()}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                value.encode(),
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), boundary


def submit(
    root: Path,
    slug: str,
    submission: Path,
    sample: Path,
    message: str,
) -> dict[str, Any]:
    """検証済みのCSVを Kaggle にアップロードし、提出を確定する。"""
    validation = validate_submission(submission, sample)
    headers = auth_header(root)
    if headers is None:
        raise KaggleError("Kaggle の認証情報がありません。")

    stat = submission.stat()
    start = _json_request(
        _submission_url(),
        headers,
        method="POST",
        payload={
            "competitionName": slug,
            "contentLength": stat.st_size,
            "lastModifiedEpochSeconds": int(stat.st_mtime),
            "fileName": submission.name,
        },
    )
    create_url = start.get("createUrl") or start.get("create_url")
    token = start.get("token")
    if not create_url or not token:
        raise KaggleError("Kaggle からアップロード先を取得できませんでした。")

    upload_request = urllib.request.Request(
        str(create_url),
        data=submission.read_bytes(),
        method="PUT",
        headers={"Content-Length": str(stat.st_size), "User-Agent": "retail-lab"},
    )
    try:
        with urllib.request.urlopen(upload_request, timeout=300) as response:
            if response.status not in (200, 201):
                raise KaggleError(
                    f"提出CSVのアップロードに失敗しました（HTTP {response.status}）。"
                )
    except urllib.error.HTTPError as exc:
        raise KaggleError(f"提出CSVのアップロードに失敗しました（HTTP {exc.code}）。") from exc

    body, boundary = _multipart(
        {
            "blobFileTokens": str(token),
            "submissionDescription": message.strip()[:500],
        }
    )
    request = urllib.request.Request(
        _submit_url(slug),
        data=body,
        method="POST",
        headers={
            **headers,
            "Accept": "application/json",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "retail-lab",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise KaggleError(
            f"Kaggle API が提出を拒否しました（HTTP {exc.code}）。",
            _api_error_hint(exc.code, detail),
        ) from exc

    return {
        "ok": True,
        "message": result.get("message", "提出を受け付けました。"),
        "ref": result.get("ref"),
        "competition": slug,
        "description": message.strip()[:500],
        "validation": validation,
        "submitted_at": pd.Timestamp.now(tz="UTC").isoformat(),
    }


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
