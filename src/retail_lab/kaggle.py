"""Kaggle のデータ取得。コンペ slug を渡すだけで使い回せる。"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import tempfile
import time
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
    slug: str = "",
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
        raise KaggleError(*explain_api_error(exc.code, detail, slug)) from exc
    try:
        parsed: dict[str, Any] = json.loads(raw)
        return parsed
    except json.JSONDecodeError as exc:
        raise KaggleError("Kaggle API の応答を読み取れませんでした。") from exc


def _api_message(detail: str) -> str:
    try:
        payload = json.loads(detail)
    except json.JSONDecodeError:
        return detail[:500]
    message = payload.get("message") or payload.get("error")
    return str(message) if message else detail[:500]


def explain_api_error(status: int, detail: str, slug: str) -> tuple[str, str]:
    """Kaggle の応答を、次に何をすればいいかが分かる日本語にする。"""
    message = _api_message(detail)

    denied = re.search(r"Permission '([^']+)' was denied", message)
    if denied:
        scope = denied.group(1)
        # このエラーはトークンの種類ではなく、アカウントがコンペに参加していないと出る。
        # 個人トークンの作成画面に権限の選択肢はない。
        return (
            f"Kaggle が権限 {scope} を認めませんでした。コンペへの参加が済んでいないのが典型です。",
            f"{rules_url(slug)} で Join Competition を押して規約に同意してください。"
            "参加済みなら、電話番号認証の未完了、招待制コンペ、"
            "トークンの失効を順に確認してください。",
        )
    if "do not have a Team" in message or "not have a team" in message.lower():
        return (
            "このコンペにまだ参加していません（チームが未作成です）。",
            f"{rules_url(slug)} を開いて Join Competition を押し、規約に同意してください。",
        )
    if "rules" in message.lower() and "accept" in message.lower():
        return (
            "コンペ規約への同意が済んでいません。",
            f"{rules_url(slug)} で規約に同意してください。",
        )
    if status == 429 or "limit" in message.lower():
        return (
            "提出回数の上限に達した可能性があります。",
            "Kaggle の提出一覧で残り回数を確認してください（1日5回まで）。",
        )
    if status in (401, 403):
        return (
            f"Kaggle が提出を拒否しました（HTTP {status}）: {message}",
            "APIトークンの権限と、コンペへの参加状態を確認してください。",
        )
    return (f"Kaggle API が提出を拒否しました（HTTP {status}）: {message}", "")


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


def account_name(root: Path) -> str | None:
    """トークンがどのアカウントのものかを返す。参加状態の食い違いはここで分かる。"""
    headers = auth_header(root)
    if headers is None:
        return None
    try:
        hello = _json_request("https://www.kaggle.com/api/v1/hello", headers)
    except KaggleError:
        return None
    name = hello.get("userName")
    return str(name) if name else None


def competition_info(root: Path, slug: str) -> dict[str, Any] | None:
    """コンペの参加状態と提出方式を読む。"""
    headers = auth_header(root)
    if headers is None:
        return None
    url = f"https://www.kaggle.com/api/v1/competitions/list?search={slug}"
    request = urllib.request.Request(
        url, headers={**headers, "Accept": "application/json", "User-Agent": "retail-lab"}
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read())
    except (urllib.error.URLError, json.JSONDecodeError):
        return None
    items = payload if isinstance(payload, list) else [payload]
    for item in items:
        if isinstance(item, dict) and str(item.get("ref", "")).endswith(slug):
            return item
    return None


def readiness_blockers(account: str | None, info: dict[str, Any] | None, slug: str) -> list[str]:
    """提出を妨げている事実だけを並べる。"""
    who = account or "不明なアカウント"
    if info is None:
        return [f"コンペ {slug} の参加状態を確認できませんでした。"]

    blockers: list[str] = []
    if not info.get("userHasEntered"):
        blockers.append(
            f"トークンのアカウント（{who}）はこのコンペに参加していません。"
            f"同じアカウントで {rules_url(slug)} を開き、規約に同意してください。"
        )
    if info.get("submissionsDisabled"):
        blockers.append("このコンペは現在提出を受け付けていません。")
    if info.get("isKernelsSubmissionsOnly"):
        blockers.append("このコンペはノートブック経由の提出のみを認めています。")
    return blockers


def check_submit_access(root: Path, slug: str, submission: Path) -> dict[str, Any]:
    """提出の1段目だけを試し、権限と参加状態を先に確かめる。

    ここで得るアップロードURLは使わずに捨てる。CSVは送らないので提出は発生しない。
    """
    headers = auth_header(root)
    if headers is None:
        return {
            "ok": False,
            "message": "Kaggle の認証情報がありません。",
            "hint": "KAGGLE_API_TOKEN を .env.local に設定してください。",
        }

    account = account_name(root)
    info = competition_info(root, slug)
    blockers = readiness_blockers(account, info, slug)
    if blockers:
        return {
            "ok": False,
            "message": blockers[0],
            "hint": " ".join(blockers[1:]),
            "account": account,
            "entered": bool(info.get("userHasEntered")) if info else None,
        }

    try:
        _json_request(
            _submission_url(),
            headers,
            method="POST",
            payload={
                "competitionName": slug,
                "contentLength": submission.stat().st_size if submission.exists() else 1,
                "lastModifiedEpochSeconds": int(time.time()),
                "fileName": "submission.csv",
            },
            slug=slug,
        )
    except KaggleError as exc:
        return {"ok": False, "message": str(exc), "hint": exc.hint, "account": account}
    return {
        "ok": True,
        "message": f"提出できます（アカウント {account}）。",
        "hint": "",
        "account": account,
        "entered": True,
    }


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
        slug=slug,
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
        raise KaggleError(*explain_api_error(exc.code, detail, slug)) from exc

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
