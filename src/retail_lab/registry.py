"""扱っているコンペの一覧。1つ足すときはここに1行足す。"""

from __future__ import annotations

from types import ModuleType

from retail_lab.competition import CompetitionSpec
from retail_lab.competitions import store_sales

_MODULES: tuple[ModuleType, ...] = (store_sales,)

COMPETITIONS: dict[str, ModuleType] = {module.SPEC.slug: module for module in _MODULES}
DEFAULT_SLUG = store_sales.SPEC.slug


def get(slug: str) -> ModuleType:
    try:
        return COMPETITIONS[slug]
    except KeyError:
        known = ", ".join(sorted(COMPETITIONS))
        raise KeyError(f"未登録のコンペです: {slug}（登録済み: {known}）") from None


def spec(slug: str) -> CompetitionSpec:
    result: CompetitionSpec = get(slug).SPEC
    return result


def specs() -> list[CompetitionSpec]:
    return [module.SPEC for module in _MODULES]
