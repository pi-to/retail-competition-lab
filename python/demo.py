"""コンペと同じ列名・日付ルールの縮小データ。本物の CSV が無くても手法を再現できる。"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

FAMILIES = [
    "GROCERY I",
    "BEVERAGES",
    "PRODUCE",
    "CLEANING",
    "DAIRY",
    "BREAD/BAKERY",
]
STORES = [
    {"store_nbr": 1, "city": "Quito", "state": "Pichincha", "type": "D", "cluster": 13},
    {"store_nbr": 3, "city": "Quito", "state": "Pichincha", "type": "D", "cluster": 8},
    {"store_nbr": 44, "city": "Quito", "state": "Pichincha", "type": "A", "cluster": 5},
    {"store_nbr": 50, "city": "Guayaquil", "state": "Guayas", "type": "A", "cluster": 14},
]


def generate_demo(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(42)

    train_end = pd.Timestamp("2017-08-15")
    test_end = pd.Timestamp("2017-08-31")
    start = pd.Timestamp("2017-01-01")
    all_dates = pd.date_range(start, test_end, freq="D")
    train_dates = all_dates[all_dates <= train_end]
    test_dates = all_dates[all_dates > train_end]

    stores = pd.DataFrame(STORES)
    stores.to_csv(data_dir / "stores.csv", index=False)

    t = np.arange(len(all_dates))
    oil = pd.DataFrame(
        {
            "date": all_dates,
            "dcoilwtico": 45 + 4 * np.sin(t / 18) + rng.normal(0, 0.6, len(t)),
        }
    )
    oil.loc[oil["date"].dt.weekday >= 5, "dcoilwtico"] = np.nan
    oil.to_csv(data_dir / "oil.csv", index=False)

    holidays = pd.DataFrame(
        [
            {"date": "2017-01-01", "type": "Holiday", "locale": "National", "locale_name": "Ecuador", "description": "New Year", "transferred": False},
            {"date": "2017-02-27", "type": "Holiday", "locale": "National", "locale_name": "Ecuador", "description": "Carnival", "transferred": False},
            {"date": "2017-04-14", "type": "Holiday", "locale": "National", "locale_name": "Ecuador", "description": "Good Friday", "transferred": False},
            {"date": "2017-05-01", "type": "Holiday", "locale": "National", "locale_name": "Ecuador", "description": "Labor Day", "transferred": False},
            {"date": "2017-05-24", "type": "Holiday", "locale": "National", "locale_name": "Ecuador", "description": "Battle of Pichincha", "transferred": False},
            {"date": "2017-08-10", "type": "Holiday", "locale": "National", "locale_name": "Ecuador", "description": "Independence", "transferred": False},
            {"date": "2017-08-15", "type": "Holiday", "locale": "Local", "locale_name": "Quito", "description": "Fundacion de Quito", "transferred": False},
            {"date": "2017-08-24", "type": "Holiday", "locale": "National", "locale_name": "Ecuador", "description": "Demo National", "transferred": False},
        ]
    )
    holidays.to_csv(data_dir / "holidays_events.csv", index=False)

    holiday_dates = set(pd.to_datetime(holidays["date"]))
    family_level = {
        "GROCERY I": 420,
        "BEVERAGES": 280,
        "PRODUCE": 160,
        "CLEANING": 90,
        "DAIRY": 130,
        "BREAD/BAKERY": 70,
    }
    store_mult = {1: 0.7, 3: 1.1, 44: 1.8, 50: 1.2}

    rows_train: list[dict] = []
    rows_test: list[dict] = []
    tx_rows: list[dict] = []
    row_id = 0

    for store in STORES:
        sn = store["store_nbr"]
        for d in all_dates:
            dow = d.weekday()
            weekend = 1.15 if dow >= 5 else 1.0
            payday = 1.18 if d.day in (15,) or d == (d + pd.offsets.MonthEnd(0)) else 1.0
            hol = 1.25 if d in holiday_dates else 1.0
            tx_rows.append(
                {
                    "date": d.strftime("%Y-%m-%d"),
                    "store_nbr": sn,
                    "transactions": int(1400 * store_mult[sn] * weekend * payday * hol + rng.normal(0, 40)),
                }
            )

        for fam in FAMILIES:
            base = family_level[fam] * store_mult[sn]
            for d in all_dates:
                dow = d.weekday()
                weekly = 1.0 + 0.12 * np.sin(2 * np.pi * (dow / 7) + hash(fam) % 5)
                payday = 1.16 if d.day in (15,) or d == (d + pd.offsets.MonthEnd(0)) else 1.0
                hol = 1.3 if d in holiday_dates else 1.0
                promo = int(rng.random() < 0.12) * int(rng.integers(1, 12))
                promo_lift = 1.0 + 0.08 * promo
                noise = rng.lognormal(0, 0.18)
                sales = max(0.0, base * weekly * payday * hol * promo_lift * noise)
                if fam == "BREAD/BAKERY" and sn == 1:
                    sales *= 0.15
                rec = {
                    "id": row_id,
                    "date": d.strftime("%Y-%m-%d"),
                    "store_nbr": sn,
                    "family": fam,
                    "onpromotion": promo,
                }
                if d <= train_end:
                    rec["sales"] = round(float(sales), 3)
                    rows_train.append(rec)
                else:
                    rows_test.append(rec)
                row_id += 1

    train = pd.DataFrame(rows_train)
    test = pd.DataFrame(rows_test)
    train.to_csv(data_dir / "train.csv", index=False)
    test.to_csv(data_dir / "test.csv", index=False)
    pd.DataFrame(tx_rows).to_csv(data_dir / "transactions.csv", index=False)
    pd.DataFrame({"id": test["id"], "sales": 0.0}).to_csv(data_dir / "sample_submission.csv", index=False)
    meta = {
        "note": "Synthetic Favorita-shaped sample. Replace with official Kaggle CSVs for a real submission.",
        "train_dates": [str(train_dates.min().date()), str(train_dates.max().date())],
        "test_dates": [str(test_dates.min().date()), str(test_dates.max().date())],
        "n_series": len(STORES) * len(FAMILIES),
    }
    (data_dir / "README.txt").write_text(
        "\n".join(f"{k}: {v}" for k, v in meta.items()) + "\n",
        encoding="utf-8",
    )
