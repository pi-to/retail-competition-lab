"""コンペを1つ足すときに埋める型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import pandas as pd


@dataclass(frozen=True)
class CompetitionSpec:
    """コンペの顔になる情報。画面の見出しと保存先がここで決まる。"""

    slug: str
    title: str
    kaggle_slug: str
    required_files: tuple[str, ...]
    horizon: int
    unit: str
    target_label: str
    method: tuple[dict[str, str], ...] = field(default=())


@dataclass
class Prepared:
    """共通の実験ループに渡す形。

    ``panel`` は学習行と提出行を縦に積んだもの。提出行は ``target`` が欠損。
    売上ラグなどの特徴は、この段階で作り終えている前提。
    """

    spec: CompetitionSpec
    source: str
    panel: pd.DataFrame
    features: list[str]
    categoricals: list[str]
    covariates: list[str]
    extra: dict[str, Any] = field(default_factory=dict)


class Competition(Protocol):
    """各コンペのモジュールが満たす約束。"""

    SPEC: CompetitionSpec

    def prepare(self, root: Path, source: str) -> Prepared: ...


def data_dir(root: Path, slug: str, source: str) -> Path:
    return root / "data" / slug / source


def output_dir(root: Path, slug: str) -> Path:
    return root / "outputs" / slug
