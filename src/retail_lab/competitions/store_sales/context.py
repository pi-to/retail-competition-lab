"""予測起点までに確定している横断特徴。再帰・一括の両方から使う。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from retail_lab import DATE, SERIES_ID, TARGET

FAMILY_TREND_FEATURES = [
    "family_mean_7",
    "family_mean_28",
    "family_level_ratio_7_56",
    "family_same_dow_4",
]
PROMO_CONTEXT_FEATURES = [
    "family_promo_mean",
    "family_promo_vs_normal",
    "store_promo_share",
]
PEER_FEATURES = [
    "cluster_family_mean_7",
    "cluster_family_level_ratio_7_56",
    "city_family_mean_7",
    "city_family_level_ratio_7_56",
    "store_to_family_ratio_28",
]


def rolling_group_states(
    frame: pd.DataFrame,
    keys: list[str],
    prefix: str,
) -> pd.DataFrame:
    """グループの日次平均から、直近の勢いを日ごとに作る。"""
    mean_7 = f"{prefix}_mean_7"
    mean_28 = f"{prefix}_mean_28"
    ratio = f"{prefix}_level_ratio_7_56"
    same_dow = f"{prefix}_same_dow_4"
    daily = (
        frame.groupby([*keys, DATE])[TARGET]
        .mean()
        .rename(TARGET)
        .reset_index()
        .sort_values([*keys, DATE])
    )
    pieces: list[pd.DataFrame] = []
    for _, group in daily.groupby(keys, sort=False):
        part = group.copy()
        values = part[TARGET].astype(float)
        part[mean_7] = values.rolling(7, min_periods=7).mean()
        part[mean_28] = values.rolling(28, min_periods=28).mean()
        far = values.rolling(56, min_periods=28).mean()
        part[ratio] = (part[mean_7] + 1.0) / (far + 1.0)
        part[same_dow] = pd.concat([values.shift(lag) for lag in (7, 14, 21, 28)], axis=1).mean(
            axis=1
        )
        keep = [c for c in [mean_7, mean_28, ratio, same_dow] if c in part.columns]
        pieces.append(part[[*keys, DATE, *keep]])
    return pd.concat(pieces, ignore_index=True)


def family_states(frame: pd.DataFrame) -> pd.DataFrame:
    """各売り場の全店舗平均から、共通する直近の勢いを日ごとに作る。"""
    states = rolling_group_states(frame, ["family"], "family")
    return states[["family", DATE, *FAMILY_TREND_FEATURES]]


def attach_promo_context(
    frame: pd.DataFrame,
    history: pd.DataFrame,
) -> pd.DataFrame:
    """全店で同じ売り場をどれだけ特売にしているかを足す。

    特売の予定は提出期間も分かっているので、未来の値をそのまま使ってよい。
    売上（target）は一切見ない。平常時の強さだけを学習期間から作る。
    """
    out = frame.copy()
    daily = frame.groupby(["family", DATE])["onpromotion"].mean().rename("family_promo_mean")
    normal = (
        history.groupby(["family", DATE])["onpromotion"]
        .mean()
        .groupby("family")
        .mean()
        .rename("family_promo_normal")
    )
    keys = pd.MultiIndex.from_arrays([out["family"], out[DATE]])
    family_mean = daily.reindex(keys).to_numpy()
    family_normal = out["family"].map(normal).to_numpy()
    out["family_promo_mean"] = family_mean
    out["family_promo_vs_normal"] = (family_mean + 1.0) / (family_normal + 1.0)
    out["store_promo_share"] = (out["onpromotion"].to_numpy() + 1.0) / (family_mean + 1.0)
    return out


def peer_states(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """クラスター・都市の同売り場勢いと、店が売り場平均に対して強いか。"""
    cluster = rolling_group_states(frame, ["cluster", "family"], "cluster_family")[
        ["cluster", "family", DATE, "cluster_family_mean_7", "cluster_family_level_ratio_7_56"]
    ]
    city = rolling_group_states(frame, ["city", "family"], "city_family")[
        ["city", "family", DATE, "city_family_mean_7", "city_family_level_ratio_7_56"]
    ]
    store = (
        frame.groupby([SERIES_ID, "family", DATE])[TARGET]
        .mean()
        .rename(TARGET)
        .reset_index()
        .sort_values([SERIES_ID, DATE])
    )
    store["store_mean_28"] = store.groupby(SERIES_ID)[TARGET].transform(
        lambda s: s.rolling(28, min_periods=28).mean()
    )
    family = family_states(frame)[["family", DATE, "family_mean_28"]]
    store = store.merge(family, on=["family", DATE], how="left")
    store["store_to_family_ratio_28"] = (store["store_mean_28"] + 1.0) / (
        store["family_mean_28"] + 1.0
    )
    return (
        cluster,
        city,
        store[[SERIES_ID, DATE, "store_to_family_ratio_28"]],
    )


def attach_by_origin(
    frame: pd.DataFrame,
    states: pd.DataFrame,
    keys: list[str],
    feature_names: list[str],
    horizons: pd.Series | np.ndarray,
    *,
    fixed_origin: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """各予測行に、予測起点までに確定したグループ特徴を付ける。"""
    out = frame.copy()
    horizon_values = (
        horizons.to_numpy(dtype=int)
        if isinstance(horizons, pd.Series)
        else np.asarray(horizons, dtype=int)
    )
    origins = (
        pd.to_datetime(out[DATE]) - pd.to_timedelta(horizon_values, unit="D")
        if fixed_origin is None
        else pd.Series(fixed_origin, index=out.index)
    )
    lookup = out[keys].copy()
    lookup["_origin"] = origins.to_numpy()
    merged = lookup.merge(
        states.rename(columns={DATE: "_origin"}),
        on=[*keys, "_origin"],
        how="left",
    )
    for name in feature_names:
        out[name] = merged[name].to_numpy()
    return out


def attach_family_trend_as_of_previous_day(
    frame: pd.DataFrame, states: pd.DataFrame
) -> pd.DataFrame:
    """学習行向け。その日の予測には前日までの売り場勢いだけを使う。"""
    out = frame.copy()
    lookup = out[["family", DATE]].copy()
    lookup["_origin"] = pd.to_datetime(lookup[DATE]) - pd.Timedelta(days=1)
    merged = lookup.merge(
        states.rename(columns={DATE: "_origin"}),
        on=["family", "_origin"],
        how="left",
    )
    for name in FAMILY_TREND_FEATURES:
        out[name] = merged[name].to_numpy()
    return out
