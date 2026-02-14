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

### Large CSVs (split for GitHub)

CSVs over 100MB are split into two files so they fit under GitHub’s file size limit:

| Original (optional to keep) | Use these in repo instead (each &lt; 100MB) |
|----------------------------|----------------------------------|
| `appearances.csv`          | `appearances_part1.csv`, `appearances_part2.csv` |
| `game_events.csv`          | `game_events_part1.csv`, `game_events_part2.csv` |
| `game_lineups.csv`         | `game_lineups_part1.csv`, `game_lineups_part2.csv`, `game_lineups_part3.csv` |

- **To create the split files**: run `.\split_large_csvs.ps1` (PowerShell) or `python split_large_csvs.py` (Python). The script splits any CSV over 100MB into as many parts as needed so each part is under 100MB. Then you can delete the originals and commit only the `_part1`, `_part2`, … files.
- **Loading**: The dashboard uses a single loader: for any dataset it looks for `name.csv` first; if missing, it loads `name_part1.csv`, `name_part2.csv`, … (in order) and concatenates them. So the same code works with either single or split sources.

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
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
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
