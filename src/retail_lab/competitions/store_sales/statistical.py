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


def last_year_fit_predict(
    train: pd.DataFrame,
    future: pd.DataFrame,
    *,
    level_window: int = LEVEL_WINDOW,
    smooth_days: int = 3,
    max_lift: float = 6.0,
) -> tuple[pd.DataFrame, list[dict[str, float | str]]]:
    """去年の同じ日から「山の形」だけを借り、水準はいまのものを使う。

    提出期間は8月後半で、新学期の文具のように暦でしか説明できない山がある。
    直近の履歴だけを見るモデルはこの山を知らないが、去年の同じ日なら知っている。

    去年の売上をそのまま出すと、たまにしか売れない棚では0が並んでしまう。そこで
    去年の値は「去年の平常時の何倍か」という倍率にしてから、いまの水準へ掛ける。
    去年の履歴が無い系列では倍率が1に近づき、直近の水準がそのまま残る。

    `future[TARGET]` は読まない。去年の実績と学習期間の水準だけを使う。
    """
    history = train[[SERIES_ID, DATE, TARGET]].copy()
    history[TARGET] = history[TARGET].astype(float).clip(lower=0)
    last_day = history[DATE].max()

    def window_mean(end: pd.Timestamp) -> pd.Series:
        part = history[
            (history[DATE] > end - pd.Timedelta(days=level_window)) & (history[DATE] <= end)
        ]
        return part.groupby(SERIES_ID)[TARGET].mean()

    now_level = window_mean(last_day)
    then_level = window_mean(last_day - pd.Timedelta(days=365))

    daily = history.set_index([SERIES_ID, DATE])[TARGET]
    out = future[[ROW_ID, DATE, SERIES_ID]].copy()
    offsets = range(-smooth_days, smooth_days + 1)
    stacked = []
    for offset in offsets:
        keys = pd.MultiIndex.from_arrays(
            [
                out[SERIES_ID].astype(str).to_numpy(),
                (pd.to_datetime(out[DATE]) - pd.Timedelta(days=365 - offset)).to_numpy(),
            ]
        )
        stacked.append(daily.reindex(keys).to_numpy(dtype=float))
    # 去年の同じ日が休みや欠品だと跳ねるので、前後数日の中央値で均す。
    # 去年の履歴が丸ごと無い行は中央値を取れない。その行は下で直近の水準へ落とす。
    window = np.column_stack(stacked)
    last_year = np.full(len(window), np.nan)
    known = ~np.isnan(window).all(axis=1)
    if known.any():
        last_year[known] = np.nanmedian(window[known], axis=1)

    series = out[SERIES_ID].astype(str)
    level = series.map(now_level).to_numpy(dtype=float)
    base = series.map(then_level).to_numpy(dtype=float)
    # 「去年の平常時の何倍だったか」。去年の履歴が無ければ 1 倍、つまり水準そのまま。
    factor = np.where(
        np.isfinite(last_year) & np.isfinite(base),
        (last_year + 1.0) / (np.nan_to_num(base, nan=0.0) + 1.0),
        1.0,
    )
    factor = np.clip(factor, 1.0 / max_lift, max_lift)
    out["pred"] = np.clip(np.nan_to_num(level, nan=0.0) * factor, 0.0, None)
    ranked: list[dict[str, float | str]] = [
        {"feature": "same_day_last_year_lift", "gain": 1.0},
        {"feature": f"level_mean_{level_window}", "gain": 0.8},
        {"feature": f"median_window_{smooth_days}", "gain": 0.3},
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
