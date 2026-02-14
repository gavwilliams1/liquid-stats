# Squad value dashboard

Dashboard for squad values across the top five European leagues (Premier League, La Liga, Serie A, Bundesliga, Ligue 1), using `clubs`, `players`, and `player_valuations` CSVs.

## Features

1. **Summary view** — Timeseries chart of total squad value over time, aggregated by league (all clubs in each of the top 5 leagues).
2. **Club detail** — Pick a league, then a club (sorted by name). Two tabs:
   - **Squad value over time** — Chart of that club’s squad value over time (from `player_valuations`).
   - **Player values** — Table of current squad with each player’s market value (from `players.csv`).

## Data links

- **Leagues**: `competitions.csv` → top 5 leagues via `is_major_national_league = true` (GB1, ES1, IT1, L1, FR1).
- **Clubs**: `clubs.csv` → filtered by `domestic_competition_id` in those leagues; joined to competition names.
- **Squad value over time**: `player_valuations.csv` → `current_club_id` → club; summed by month and (for summary) by league.
- **Player table**: `players.csv` → `current_club_id` and `market_value_in_eur` for the selected club.

### Date columns (time-based CSVs)

Summarised from current CSVs (first/last row sampled where Python wasn’t available):

| CSV | Date column | Observed range |
|-----|-------------|----------------|
| **appearances** | `date` (6th col) | 2012-07-03 to 2026-12-02 |
| **game_events** | `date` (2nd col) | 2012-08-05 to 2026-11-02 |
| **game_lineups** | `date` (2nd col) | 2013-07-27 to 2024-03-16 (last row sampled; file has multiline fields) |
| **games** | `date` (5th col) | 2013-11-22 to 2021-11-06 (first/last row; file order may not be by date; also has `season`) |
| **player_valuations** | `date` (2nd col) | 2000-01-20 to 2025-06-09 |

All use **YYYY-MM-DD**. Run `python summarise_dates.py` for exact min/max and row counts (script streams, so it works on large files).

### Large CSVs (split for GitHub)

GitHub has a **100MB per-file** limit. CSVs over 100MB can be split into smaller files (each with the **same column headings**) so they can be pushed via git:

| Original (optional to keep) | Use in repo instead (each &lt; 100MB) |
|----------------------------|--------------------------------------|
| `appearances.csv`          | `appearances_part1.csv`, `appearances_part2.csv`, … |
| `game_events.csv`          | `game_events_part1.csv`, `game_events_part2.csv`, … |
| `game_lineups.csv`         | `game_lineups_part1.csv`, `game_lineups_part2.csv`, … |

- **To create the split files**: run `.\split_large_csvs.ps1` (PowerShell) or `python split_large_csvs.py`. The script finds any CSV ≥ 100MB, removes old `_part*.csv` for that name, and writes new parts (each &lt; 100MB, same header in every part). Commit the `_part1`, `_part2`, … files; you can omit or add the originals to `.gitignore` if you don’t want to push them.
- **Loading**: The dashboard’s `load_csv()` looks for `name.csv` first; if missing, it loads `name_part1.csv`, `name_part2.csv`, … in order and concatenates them. Same code works with single or split sources.
- **Recut so splits include data through 2026**: If your part files were created from an older source and stop around Q1 2025, do this: (1) Run `.\merge_part_csvs.ps1` or `python merge_part_csvs.py` to merge existing part files into `appearances.csv`, `game_events.csv`, `game_lineups.csv`. (2) Replace those merged files with your **complete** source files that contain all records through 2026 (or append the missing 2025/2026 rows to the merged files). (3) Run `.\split_large_csvs.ps1` or `python split_large_csvs.py` to re-split; the script overwrites old part files and keeps each new part under 100MB. All records into 2026 will then be in the new part files.

---

## Deploy to the cloud (no Python needed on your machine)

Use **Streamlit Community Cloud** to run the dashboard and get a public URL.

### 1. Put the project on GitHub

- Create a new repository on [GitHub](https://github.com/new) (e.g. `liquid-stats`).
- **Include CSV data** in the repo. For the dashboard you need: `clubs.csv`, `competitions.csv`, `players.csv`, `player_valuations.csv`. For large tables use the split files only (e.g. `appearances_part1.csv`, `appearances_part2.csv`) so each file is under 100MB.
- Push this folder to the repo. From your project folder:

```bash
git init
git add dashboard.py requirements.txt README.md .streamlit .gitignore
git add split_large_csvs.ps1 split_large_csvs.py
git add clubs.csv competitions.csv players.csv player_valuations.csv
git add appearances_part1.csv appearances_part2.csv
git add game_events_part1.csv game_events_part2.csv
git add game_lineups_part1.csv game_lineups_part2.csv game_lineups_part3.csv
git commit -m "Add squad value dashboard"
git branch -M main
git remote add origin https://github.com/gavwilliams1/liquid-stats.git
git push -u origin main
```

Omit the large original CSVs (`appearances.csv`, `game_events.csv`, `game_lineups.csv`) if you only use the split parts.

### 2. Deploy on Streamlit Community Cloud

1. Go to **[share.streamlit.io](https://share.streamlit.io)**.
2. Sign in with your **GitHub** account.
3. Click **“New app”**.
4. Choose:
   - **Repository**: `YOUR_USERNAME/YOUR_REPO_NAME`
   - **Branch**: `main`
   - **Main file path**: `dashboard.py`
5. Click **“Deploy!”**.

After a few minutes you’ll get a URL like:

**`https://YOUR_REPO_NAME.streamlit.app`**

You can share that link; the app runs in the cloud and doesn’t require Python on your computer.

---

## Run locally (optional)

If you have Python installed:

```bash
pip install -r requirements.txt
streamlit run dashboard.py
```

Then open the URL shown in the terminal (usually http://localhost:8501).
# liquid-stats
Gav's messing around with glorious football stats
