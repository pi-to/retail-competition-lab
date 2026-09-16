"""Kaggle の公式データを API から取る。認証は環境変数か kaggle.json。"""

from __future__ import annotations

import base64
import io
import json
import os
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

COMPETITION = "store-sales-time-series-forecasting"
DOWNLOAD_URL = f"https://www.kaggle.com/api/v1/competitions/data/download-all/{COMPETITION}"
RULES_URL = f"https://www.kaggle.com/competitions/{COMPETITION}/rules"
TOKEN_URL = "https://www.kaggle.com/settings"
REQUIRED = [
    "train.csv",
    "test.csv",
    "stores.csv",
    "oil.csv",
    "holidays_events.csv",
    "transactions.csv",
]


class KaggleError(RuntimeError):
    """利用者に見せる想定のメッセージを持つ例外。"""

    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.hint = hint


def find_credentials(root: Path) -> tuple[str, str] | None:
    user = os.environ.get("KAGGLE_USERNAME")
    key = os.environ.get("KAGGLE_KEY")
    if user and key:
        return user, key
    for candidate in (root / "kaggle.json", Path.home() / ".kaggle" / "kaggle.json"):
        if candidate.exists():
            try:
                blob = json.loads(candidate.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise KaggleError(
                    f"{candidate} が JSON として読めません。",
                    "Kaggle からダウンロードした kaggle.json をそのまま置いてください。",
                ) from exc
            if blob.get("username") and blob.get("key"):
                return str(blob["username"]), str(blob["key"])
    return None


def data_dir(root: Path) -> Path:
    return root / "data" / "kaggle"


def missing_files(root: Path) -> list[str]:
    target = data_dir(root)
    return [name for name in REQUIRED if not (target / name).exists()]


def status(root: Path) -> dict:
    missing = missing_files(root)
    try:
        creds = find_credentials(root)
        cred_error = ""
    except KaggleError as exc:
        creds = None
        cred_error = str(exc)
    return {
        "competition": COMPETITION,
        "ready": not missing,
        "missing": missing,
        "has_credentials": creds is not None,
        "credential_error": cred_error,
        "rules_url": RULES_URL,
        "token_url": TOKEN_URL,
    }


def download(root: Path) -> dict:
    """公式データを取得して data/kaggle に展開する。"""
    creds = find_credentials(root)
    if creds is None:
        raise KaggleError(
            "Kaggle の認証情報がありません。",
            "Kaggle の Settings で API トークンを作り、KAGGLE_USERNAME と KAGGLE_KEY を設定するか、"
            "kaggle.json をリポジトリ直下に置いてください。",
        )
    user, key = creds
    token = base64.b64encode(f"{user}:{key}".encode()).decode()
    request = urllib.request.Request(
        DOWNLOAD_URL,
        headers={"Authorization": f"Basic {token}", "User-Agent": "store-sales-lab"},
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise KaggleError(
                "Kaggle が認証またはアクセスを拒否しました。",
                "トークンが有効かを確かめ、コンペのページで規約に同意してください（Join Competition）。",
            ) from exc
        raise KaggleError(f"Kaggle への接続が失敗しました（HTTP {exc.code}）。") from exc
    except urllib.error.URLError as exc:
        raise KaggleError(f"Kaggle に接続できません: {exc.reason}") from exc

    target = data_dir(root)
    target.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            for name in archive.namelist():
                base = Path(name).name
                if base in REQUIRED or base == "sample_submission.csv":
                    with archive.open(name) as src, (target / base).open("wb") as dst:
                        dst.write(src.read())
    except zipfile.BadZipFile as exc:
        raise KaggleError(
            "受け取ったファイルが zip ではありませんでした。",
            "コンペの規約に同意していない場合、Kaggle は HTML を返します。",
        ) from exc

    missing = missing_files(root)
    if missing:
        raise KaggleError(f"取得できたが不足しています: {', '.join(missing)}")
    sizes = {name: (target / name).stat().st_size for name in REQUIRED}
    return {"ok": True, "dir": str(target), "sizes": sizes}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Kaggle 公式データの取得")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    if args.status:
        print(json.dumps(status(args.root), ensure_ascii=False, indent=2))
    else:
        try:
            print(json.dumps(download(args.root), ensure_ascii=False, indent=2))
        except KaggleError as exc:
            print(json.dumps({"ok": False, "error": str(exc), "hint": exc.hint}, ensure_ascii=False, indent=2))
            raise SystemExit(1)
