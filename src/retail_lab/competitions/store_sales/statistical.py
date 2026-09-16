"""木を使わない統計手法。売れない日が多い棚に、別の外し方を持ち込む。

LightGBM はどの版も同じ表を見ているので、外れる行が似てくる。
ここでは「売れる頻度と売れたときの量を別に平滑化する」古典手法（TSB）と、
「直近の水準 × 売り場の曜日のクセ」だけで出す版を用意する。
混合はモデルの数ではなく外し方の違いで効くので、単体の点数が低くても意味がある。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from retail_lab import DATE, ROW_ID, SERIES_ID, TARGET

OUTPUT = [ROW_ID, DATE, SERIES_ID, "pred"]
LEVEL_WINDOW = 28
DOW_WINDOW = 112
SALE_THRESHOLD = 0.5


def _tsb_state(values: np.ndarray, alpha: float, beta: float) -> float:
    """売れる確率と売れたときの量を別に平滑化し、掛けた値を返す。

    Teunter-Syntetos-Babai 法。売れない日にも確率だけを下げるので、
    「最近さっぱり売れない棚」を控えめに、しかしゼロには潰さずに出せる。
    """
    if values.size == 0:
        return 0.0
    sold = values >= SALE_THRESHOLD
    probability = float(sold.mean())
    sizes = values[sold]
    size = float(sizes.mean()) if sizes.size else 0.0
    for value, is_sale in zip(values, sold, strict=True):
        if is_sale:
            probability += alpha * (1.0 - probability)
            size += beta * (float(value) - size)
        else:
            probability += alpha * (0.0 - probability)
    return max(probability, 0.0) * max(size, 0.0)


def _series_history(train: pd.DataFrame, days: int) -> dict[str, np.ndarray]:
    cutoff = train[DATE].max() - pd.Timedelta(days=days)
    recent = train[train[DATE] > cutoff].sort_values([SERIES_ID, DATE])
    return {
        str(sid): group[TARGET].astype(float).clip(lower=0).to_numpy()
        for sid, group in recent.groupby(SERIES_ID, sort=False)
    }


def tsb_fit_predict(
    train: pd.DataFrame,
    future: pd.DataFrame,
    *,
    alpha: float = 0.2,
    beta: float = 0.1,
    context_days: int = 180,
) -> tuple[pd.DataFrame, list[dict[str, float | str]]]:
    """系列ごとに TSB の平滑値を出し、16日間そのまま横に伸ばす。

    `future[TARGET]` は読まない。日付と行の識別子だけを使う。
    """
    histories = _series_history(train, context_days)
    levels = {sid: _tsb_state(values, alpha, beta) for sid, values in histories.items()}
    out = future[[ROW_ID, DATE, SERIES_ID]].copy()
    out["pred"] = out[SERIES_ID].astype(str).map(levels).fillna(0.0).clip(lower=0.0)
    ranked: list[dict[str, float | str]] = [
        {"feature": "tsb_probability_x_size", "gain": 1.0},
        {"feature": f"alpha={alpha:g}", "gain": 0.0},
        {"feature": f"beta={beta:g}", "gain": 0.0},
    ]
    return out[OUTPUT], ranked


def _family_dow_index(train: pd.DataFrame, days: int) -> pd.DataFrame:
    """売り場ごとに「月曜は平均の何倍か」を全店まとめて出す。"""
    cutoff = train[DATE].max() - pd.Timedelta(days=days)
    recent = train[train[DATE] > cutoff].copy()
    recent["_dow"] = pd.to_datetime(recent[DATE]).dt.weekday
    by_dow = recent.groupby(["family", "_dow"])[TARGET].mean().rename("dow_mean").reset_index()
    overall = recent.groupby("family")[TARGET].mean().rename("family_mean").reset_index()
    merged = by_dow.merge(overall, on="family", how="left")
    merged["factor"] = (merged["dow_mean"] + 1.0) / (merged["family_mean"] + 1.0)
    return merged[["family", "_dow", "factor"]]


def dow_index_fit_predict(
    train: pd.DataFrame,
    future: pd.DataFrame,
    *,
    level_window: int = LEVEL_WINDOW,
    dow_window: int = DOW_WINDOW,
) -> tuple[pd.DataFrame, list[dict[str, float | str]]]:
    """直近の水準に、売り場の曜日のクセを掛けるだけの版。

    `future[TARGET]` は読まない。水準と曜日のクセはどちらも学習期間だけから作る。
    """
    cutoff = train[DATE].max() - pd.Timedelta(days=level_window)
    level = (
        train[train[DATE] > cutoff]
        .groupby(SERIES_ID)[TARGET]
        .apply(lambda s: float(s.astype(float).clip(lower=0).mean()))
    )
    index = _family_dow_index(train, dow_window)
    out = future[[ROW_ID, DATE, SERIES_ID, "family"]].copy()
    out["_dow"] = pd.to_datetime(out[DATE]).dt.weekday
    out = out.merge(index, on=["family", "_dow"], how="left")
    out["_level"] = out[SERIES_ID].map(level).fillna(0.0)
    out["pred"] = (out["_level"] * out["factor"].fillna(1.0)).clip(lower=0.0)
    ranked: list[dict[str, float | str]] = [
        {"feature": f"level_mean_{level_window}", "gain": 1.0},
        {"feature": f"family_dow_factor_{dow_window}", "gain": 0.5},
    ]
    return out[OUTPUT], ranked
