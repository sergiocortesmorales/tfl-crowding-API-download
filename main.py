"""
TfL Crowding Data Downloader
=============================
Downloads historical crowding profiles for all London Underground stations
from the TfL Unified API, one day at a time per station.

Setup:
    pip install requests pandas

    GET A FREE API KEY AT: https://api-portal.tfl.gov.uk/
    (optional but recommended to avoid any error)

Output:
    tfl_crowding_data.csv - 15-min crowding profiles by station and day

    Columns:
        station_name, naptan_id, lat, lon, day_of_week,
        time_band, hour, pct_of_baseline

    pct_of_baseline is a fraction where 1.0 = the busiest this station
    has ever been (since July 2019). It is relative, not an absolute count.
"""

import requests
import pandas as pd
import time
import sys
from datetime import datetime

# -- Config -------------------------------------------------------------------
API_KEY = ""  # PASTE YOUR API KEY HERE!
BASE_URL = "https://api.tfl.gov.uk"
DAY_TYPES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
OUTPUT = "tfl_crowding_data.csv"
RATE_LIMIT_DELAY = 0.15  # seconds between requests


# -- Step 1: Get all tube station NaPTAN IDs ----------------------------------
def get_all_tube_stations():
    """Fetch unique tube stations by querying each LU line's stop points."""
    print("Fetching all tube stations...")
    params = {"app_key": API_KEY} if API_KEY else {}

    tube_lines = [
        "bakerloo", "central", "circle", "district", "hammersmith-city",
        "jubilee", "metropolitan", "northern", "piccadilly", "victoria",
        "waterloo-city",
    ]

    stations = {}
    for line in tube_lines:
        url = f"{BASE_URL}/Line/{line}/StopPoints"
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        for stop in resp.json():
            nid = stop.get("naptanId", "")
            if nid.startswith("940GZZLU") and nid not in stations:
                stations[nid] = {
                    "naptanId": nid,
                    "name": stop["commonName"]
                              .replace(" Underground Station", "")
                              .strip(),
                    "lat": stop.get("lat"),
                    "lon": stop.get("lon"),
                }
        time.sleep(RATE_LIMIT_DELAY)

    stations = list(stations.values())
    print(f"  Found {len(stations)} tube stations.")
    return stations


# -- Step 2: Fetch crowding for one station + one day -------------------------
def get_crowding_by_day(naptan_id, day, params):
    """
    GET /Crowding/{naptanId}/{day}
    Returns list of timeBand dicts, or None on failure.
    """
    url = f"{BASE_URL}/crowding/{naptan_id}/{day}"
    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 429:
            return "rate_limited"
        if resp.status_code != 200:
            return "error"
        data = resp.json()
        if isinstance(data, dict):
            return data.get("timeBands", [])
        elif isinstance(data, list) and data:
            return data[0].get("timeBands", [])
        return []
    except Exception as e:
        print(f"    Warning: {naptan_id}/{day} -- {e}")
        return "error"


# -- Step 3: Parse time band string to integer hour ---------------------------
def parse_hour(tb):
    """'0600-0615' -> 6"""
    try:
        return int(tb.split("-")[0][:2])
    except Exception:
        return None


# -- Main ---------------------------------------------------------------------
def main():
    params = {"app_key": API_KEY} if API_KEY else {}

    print(f"\n{'='*60}")
    print(f"  TfL Crowding Data Downloader")
    print(f"  API key: {'yes' if API_KEY else 'none (rate-limited)'}")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    stations = get_all_tube_stations()
    if not stations:
        print("ERROR: No stations retrieved. Check network / API key.")
        sys.exit(1)

    rows = []
    total = len(stations)
    stations_with_data = set()
    stations_no_data = set()
    stations_errors = set()

    for i, stn in enumerate(stations, 1):
        nid = stn["naptanId"]
        name = stn["name"]
        print(f"[{i:3d}/{total}] {name}", end="")

        got_any = False
        had_error = False
        for day in DAY_TYPES:
            bands = get_crowding_by_day(nid, day, params)
            time.sleep(RATE_LIMIT_DELAY)

            if bands == "rate_limited":
                had_error = True
                print(f" [rate limited on {day}]", end="")
                time.sleep(2)  # back off and retry once
                bands = get_crowding_by_day(nid, day, params)
                time.sleep(RATE_LIMIT_DELAY)

            if bands == "error":
                had_error = True
                continue

            if not bands:
                continue

            got_any = True
            for band in bands:
                tb = band.get("timeBand", "")
                rows.append({
                    "station_name": name,
                    "naptan_id": nid,
                    "lat": stn["lat"],
                    "lon": stn["lon"],
                    "day_of_week": day,
                    "time_band": tb,
                    "hour": parse_hour(tb),
                    "pct_of_baseline": band.get("percentageOfBaseLine"),
                })

        if got_any:
            stations_with_data.add(nid)
            print(f"  ok")
        elif had_error:
            stations_errors.add(nid)
            print(f"  -> FAILED (API error)")
        else:
            stations_no_data.add(nid)
            print(f"  -> no data")

    if not rows:
        print("\nNo data collected. Check network, API key, or TfL status.")
        sys.exit(1)

    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT, index=False)

    print(f"\nSaved: {OUTPUT}")
    print(f"  {len(df):,} rows")
    print(f"  {len(stations_with_data)} stations with data")
    print(f"  {len(stations_no_data)} stations with no data (genuine)")
    print(f"  {len(stations_errors)} stations failed (API error / rate limit)")
    print(f"  Days: {sorted(df['day_of_week'].unique())}")

    if stations_no_data:
        print(f"\nStations with no crowding data:")
        for nid in sorted(stations_no_data):
            name = next(s["name"] for s in stations if s["naptanId"] == nid)
            print(f"  {name} ({nid})")

    if stations_errors:
        print(f"\nStations that FAILED (re-run may help):")
        for nid in sorted(stations_errors):
            name = next(s["name"] for s in stations if s["naptanId"] == nid)
            print(f"  {name} ({nid})")

    print(f"\nDone: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()