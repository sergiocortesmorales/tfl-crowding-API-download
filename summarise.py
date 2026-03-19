"""
TfL Crowding Data Summariser
=============================
Reads the output of the downloader (tfl_crowding_data.csv) and produces
summary tables at different aggregation levels for spatial analysis.

Input:
    tfl_crowding_data.csv  (from the downloader script)

Output:
    tfl_crowding_daily.csv      -- mean/peak/min per station per day
    tfl_crowding_weekly_avg.csv -- single row per station (weekly average)
    tfl_crowding_peak_hours.csv -- AM and PM peak crowding per station

Usage:
    python summarise_crowding.py
"""

import pandas as pd
import sys
import os

# -- Config -------------------------------------------------------------------
INPUT = "tfl_crowding_data.csv"
OUT_DAILY = "tfl_crowding_daily.csv"
OUT_WEEKLY = "tfl_crowding_weekly_avg.csv"
OUT_PEAKS = "tfl_crowding_peak_hours.csv"


def main():
    if not os.path.exists(INPUT):
        print(f"ERROR: {INPUT} not found. Run the downloader first.")
        sys.exit(1)

    df = pd.read_csv(INPUT)
    print(f"Loaded {INPUT}: {len(df):,} rows, {df['naptan_id'].nunique()} stations")

    # -- 1. Daily summary: mean / peak / min per station per day --------------
    daily = (
        df.groupby(["station_name", "naptan_id", "lat", "lon", "day_of_week"])
        ["pct_of_baseline"]
        .agg(
            mean_pct="mean",
            peak_pct="max",
            min_pct="min",
            n_bands="count",
        )
        .reset_index()
    )
    for col in ["mean_pct", "peak_pct", "min_pct"]:
        daily[col] = daily[col].round(4)

    daily.to_csv(OUT_DAILY, index=False)
    print(f"Saved: {OUT_DAILY}  ({len(daily):,} rows)")

    # -- 2. Weekly average: single number per station -------------------------
    #    This is the most useful for a spatial join with LSOA mortality data.
    weekly = (
        daily.groupby(["station_name", "naptan_id", "lat", "lon"])
        .agg(
            weekly_mean_pct=("mean_pct", "mean"),
            weekly_peak_pct=("peak_pct", "max"),
            weekly_min_pct=("min_pct", "min"),
        )
        .reset_index()
    )
    for col in ["weekly_mean_pct", "weekly_peak_pct", "weekly_min_pct"]:
        weekly[col] = weekly[col].round(4)

    weekly.to_csv(OUT_WEEKLY, index=False)
    print(f"Saved: {OUT_WEEKLY}  ({len(weekly):,} rows)")

    # -- 3. Peak-hour crowding: AM peak (07-09) and PM peak (17-19) -----------
    am = df[df["hour"].between(7, 9)]
    pm = df[df["hour"].between(17, 19)]

    am_avg = (
        am.groupby(["station_name", "naptan_id", "lat", "lon"])
        ["pct_of_baseline"]
        .agg(am_peak_mean="mean", am_peak_max="max")
        .reset_index()
    )

    pm_avg = (
        pm.groupby(["station_name", "naptan_id", "lat", "lon"])
        ["pct_of_baseline"]
        .agg(pm_peak_mean="mean", pm_peak_max="max")
        .reset_index()
    )

    peaks = am_avg.merge(pm_avg, on=["station_name", "naptan_id", "lat", "lon"], how="outer")
    for col in peaks.columns:
        if col.endswith(("_mean", "_max")):
            peaks[col] = peaks[col].round(4)

    peaks.to_csv(OUT_PEAKS, index=False)
    print(f"Saved: {OUT_PEAKS}  ({len(peaks):,} rows)")

    # -- Preview --------------------------------------------------------------
    print(f"\n--- Top 10 busiest stations (weekly peak) ---")
    top = weekly.nlargest(10, "weekly_peak_pct")[
        ["station_name", "weekly_mean_pct", "weekly_peak_pct"]
    ]
    print(top.to_string(index=False))

    print(f"\n--- Top 10 busiest AM peak stations ---")
    top_am = peaks.nlargest(10, "am_peak_max")[
        ["station_name", "am_peak_mean", "am_peak_max"]
    ]
    print(top_am.to_string(index=False))

    print("\nDone.")


if __name__ == "__main__":
    main()