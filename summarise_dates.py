"""Summarise the 'date' column in each CSV that has time-based data.
Uses streaming (no full load) so large CSVs are handled without memory issues.
"""
import csv
import re
from pathlib import Path
from datetime import datetime

DATA_DIR = Path(__file__).resolve().parent

FILES_WITH_DATES = [
    "appearances",
    "game_events",
    "game_lineups",
    "games",
    "player_valuations",
]

DATE_COL = "date"


def _parse_date(s):
    if not s or not s.strip():
        return None
    s = s.strip()
    # Prefer YYYY-MM-DD (first 10 chars)
    if len(s) >= 10:
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d")
        except ValueError:
            pass
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def _get_files(basedir, name):
    single = basedir / f"{name}.csv"
    if single.exists():
        return [single]
    parts = sorted(
        basedir.glob(f"{name}_part*.csv"),
        key=lambda p: int(m.group(1)) if (m := re.search(r"_part(\d+)\.csv$", p.name)) else 0,
    )
    return parts if parts else []


def stream_date_range(basedir, name, col=DATE_COL):
    """Stream CSV(s) and return (row_count, valid_count, min_date, max_date)."""
    files = _get_files(basedir, name)
    if not files:
        return None
    total = 0
    valid = 0
    min_d, max_d = None, None
    for path in files:
        with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.DictReader(f)
            if col not in reader.fieldnames:
                return None
            for row in reader:
                total += 1
                d = _parse_date(row.get(col, ""))
                if d is not None:
                    valid += 1
                    min_d = d if min_d is None else min(min_d, d)
                    max_d = d if max_d is None else max(max_d, d)
    return total, valid, min_d, max_d


def main():
    print("Date column summary by CSV\n" + "=" * 60)
    for name in FILES_WITH_DATES:
        result = stream_date_range(DATA_DIR, name)
        if result is None:
            print(f"{name}: (file not found or no '{DATE_COL}' column)\n")
            continue
        total, valid, min_d, max_d = result
        if valid == 0:
            print(f"{name}: no valid dates\n")
            continue
        print(f"{name}.csv (column: '{DATE_COL}')")
        print(f"  Rows:        {total:,} (valid dates: {valid:,})")
        print(f"  Min date:    {min_d.strftime('%Y-%m-%d')}")
        print(f"  Max date:    {max_d.strftime('%Y-%m-%d')}")
        print(f"  Date range:  {(max_d - min_d).days} days")
        print()


if __name__ == "__main__":
    main()
