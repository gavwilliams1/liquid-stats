"""
Squad value dashboard: top 5 European leagues.
Links clubs, players, and player_valuations CSVs.
Supports single-file or split (_part1 / _part2) CSVs for large datasets.
"""
import re
import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent
TOP5_LEAGUES = ("GB1", "ES1", "IT1", "L1", "FR1")  # Premier League, La Liga, Serie A, Bundesliga, Ligue 1


def load_csv(basedir: Path, name: str) -> pd.DataFrame:
    """Load a CSV by base name: uses name.csv if present, else name_part1.csv, name_part2.csv, ... (all parts concatenated)."""
    single = basedir / f"{name}.csv"
    if single.exists():
        return pd.read_csv(single)
    part_files = sorted(
        basedir.glob(f"{name}_part*.csv"),
        key=lambda p: int(re.search(r"_part(\d+)\.csv$", p.name).group(1)) if re.search(r"_part(\d+)\.csv$", p.name) else 0,
    )
    if part_files:
        return pd.concat(
            [pd.read_csv(p) for p in part_files],
            ignore_index=True,
        )
    raise FileNotFoundError(f"Neither {name}.csv nor {name}_part1.csv, ... found in {basedir}")


@st.cache_data
def load_data():
    """Load and link clubs, players, valuations, competitions."""
    competitions = load_csv(DATA_DIR, "competitions")
    clubs = load_csv(DATA_DIR, "clubs")
    players = load_csv(DATA_DIR, "players")
    valuations = load_csv(DATA_DIR, "player_valuations")

    # League names for top 5
    major = competitions[competitions["competition_id"].isin(TOP5_LEAGUES)][
        ["competition_id", "name"]
    ].rename(columns={"competition_id": "league_id", "name": "league_name"})

    # Clubs in top 5 leagues
    clubs_top5 = clubs[clubs["domestic_competition_id"].isin(TOP5_LEAGUES)].copy()
    clubs_top5 = clubs_top5.merge(
        major,
        left_on="domestic_competition_id",
        right_on="league_id",
        how="left",
    )

    # Parse valuation dates
    valuations["date"] = pd.to_datetime(valuations["date"], errors="coerce")
    valuations = valuations.dropna(subset=["date"])

    return {
        "competitions": competitions,
        "clubs": clubs_top5,
        "players": players,
        "valuations": valuations,
        "league_names": major,
    }


@st.cache_data
def squad_value_by_league_over_time(clubs_top5, valuations):
    """Squad value by year: one value per year = highest total squad value in that year (per league).
    Excludes the final year if incomplete (data not through full year) to avoid a misleading drop."""
    club_ids = set(clubs_top5["club_id"])
    v = valuations[valuations["current_club_id"].isin(club_ids)].copy()
    v = v.merge(
        clubs_top5[["club_id", "league_id", "league_name"]],
        left_on="current_club_id",
        right_on="club_id",
        how="left",
    )
    v = v.dropna(subset=["league_id"])
    # Exclude last year if incomplete: if latest valuation is before Oct 1 of that year, drop that year
    max_date = v["date"].max()
    if pd.notna(max_date):
        last_year = max_date.year
        if max_date.month < 10:
            v = v[v["date"].dt.year < last_year]
    v["month"] = v["date"].dt.to_period("M")
    by_month_league = (
        v.groupby(["month", "league_id", "league_name"])
        .agg(squad_value_eur=("market_value_in_eur", "sum"))
        .reset_index()
    )
    by_month_league["year"] = by_month_league["month"].apply(lambda p: p.year)
    by_year_league = (
        by_month_league.groupby(["year", "league_id", "league_name"])
        .agg(squad_value_eur=("squad_value_eur", "max"))
        .reset_index()
    )
    by_year_league["date"] = pd.to_datetime(by_year_league["year"].astype(str) + "-06-01")
    return by_year_league


@st.cache_data
def squad_value_by_club_over_time(club_id, valuations):
    """Squad value by year for one club: one value per year = highest total in that year.
    Excludes the final year if incomplete to avoid a misleading drop."""
    v = valuations[valuations["current_club_id"] == club_id].copy()
    max_date = v["date"].max()
    if pd.notna(max_date) and max_date.month < 10:
        v = v[v["date"].dt.year < max_date.year]
    v["month"] = v["date"].dt.to_period("M")
    by_month = v.groupby("month").agg(squad_value_eur=("market_value_in_eur", "sum")).reset_index()
    by_month["year"] = by_month["month"].apply(lambda p: p.year)
    by_year = by_month.groupby("year").agg(squad_value_eur=("squad_value_eur", "max")).reset_index()
    by_year["date"] = pd.to_datetime(by_year["year"].astype(str) + "-06-01")
    return by_year


def format_eur(x):
    if pd.isna(x) or x == 0:
        return "—"
    if x >= 1e9:
        return f"€{x / 1e9:.2f}B"
    if x >= 1e6:
        return f"€{x / 1e6:.1f}M"
    if x >= 1e3:
        return f"€{x / 1e3:.1f}K"
    return f"€{x:.0f}"


# ---- Appearances (separate from squad value) ----

@st.cache_data
def load_appearances_data():
    """Load appearances, players, clubs; compute timeframe and club_ids still in each league (latest season = 2025-style)."""
    appearances = load_csv(DATA_DIR, "appearances")
    players = load_csv(DATA_DIR, "players")
    clubs = load_csv(DATA_DIR, "clubs")
    appearances["_date"] = pd.to_datetime(appearances["date"], errors="coerce")
    valid = appearances["_date"].dropna()
    year_min = int(valid.min().year) if len(valid) else None
    year_max = int(valid.max().year) if len(valid) else None
    appearances = appearances.drop(columns=["_date"])
    # Clubs still in each league: use latest season in dataset (e.g. 2024/2025)
    clubs_top5 = clubs[clubs["domestic_competition_id"].isin(TOP5_LEAGUES)].copy()
    clubs_top5["last_season_num"] = pd.to_numeric(clubs_top5["last_season"], errors="coerce")
    latest_season = clubs_top5["last_season_num"].max()
    club_ids_per_league = {}
    for league_id in TOP5_LEAGUES:
        in_league = clubs_top5[
            (clubs_top5["domestic_competition_id"] == league_id)
            & (clubs_top5["last_season_num"] == latest_season)
        ]
        club_ids_per_league[league_id] = set(in_league["club_id"].dropna().astype(int))
    return appearances, players, year_min, year_max, club_ids_per_league


@st.cache_data
def appearances_top10_in_league(
    league_id: str,
    league_name: str,
    appearances: pd.DataFrame,
    players: pd.DataFrame,
    club_ids_current: set,
) -> pd.DataFrame:
    """Top 10 players still in this league (current club in league as of latest season) by appearances in this league."""
    current_in_league = players[
        players["current_club_id"].notna()
        & players["current_club_id"].astype(int).isin(club_ids_current)
    ][["player_id", "name"]].drop_duplicates(subset=["player_id"])
    app_in_league = appearances[appearances["competition_id"] == league_id]
    counts = app_in_league.groupby("player_id").size().reset_index(name="appearances")
    merged = counts.merge(current_in_league, on="player_id", how="inner")
    top10 = merged.nlargest(10, "appearances")
    top10["league_name"] = league_name
    return top10


@st.cache_data
def appearances_top10_top5_leagues(appearances: pd.DataFrame, players: pd.DataFrame) -> pd.DataFrame:
    """Top 10 current players (current club in top 5 league) by total appearances (all competitions)."""
    current_top5 = players[
        players["current_club_domestic_competition_id"].isin(TOP5_LEAGUES)
        & players["current_club_id"].notna()
    ][["player_id", "name"]].drop_duplicates(subset=["player_id"])
    counts = appearances.groupby("player_id").size().reset_index(name="appearances")
    merged = counts.merge(current_top5, on="player_id", how="inner")
    return merged.nlargest(10, "appearances")


@st.cache_data
def appearances_top10_all_leagues(appearances: pd.DataFrame, players: pd.DataFrame) -> pd.DataFrame:
    """Top 10 current players (any league) by total appearances (all competitions)."""
    current_any = players[players["current_club_id"].notna()][["player_id", "name"]].drop_duplicates(subset=["player_id"])
    counts = appearances.groupby("player_id").size().reset_index(name="appearances")
    merged = counts.merge(current_any, on="player_id", how="inner")
    return merged.nlargest(10, "appearances")


# Professional chart styling (Athletic-inspired)
CHART_FONT = "Georgia, 'Times New Roman', serif"
CHART_BAR_COLOR = "#c93434"
CHART_BG = "rgba(0,0,0,0)"
CHART_MARGIN = dict(t=60, b=50, l=20, r=20)


def _bar_chart_appearances(
    df: pd.DataFrame,
    title: str,
    timeframe_str: str,
    y_label: str = "Appearances",
) -> None:
    """Render a horizontal bar chart for appearance counts with timeframe."""
    if df.empty:
        st.info(f"No data for {title}.")
        return
    df = df.sort_values("appearances", ascending=True)
    fig = px.bar(
        df,
        x="appearances",
        y="name",
        orientation="h",
        labels={"appearances": y_label, "name": "Player"},
        title=title,
        text="appearances",
    )
    fig.update_traces(
        textposition="outside",
        marker_color=CHART_BAR_COLOR,
        textfont=dict(family=CHART_FONT, size=12),
    )
    fig.update_layout(
        yaxis_categoryorder="total ascending",
        showlegend=False,
        height=400,
        margin=CHART_MARGIN,
        paper_bgcolor=CHART_BG,
        plot_bgcolor=CHART_BG,
        font=dict(family=CHART_FONT, size=13, color="#1a1a1a"),
        title=dict(font=dict(size=18), x=0, xanchor="left"),
        xaxis=dict(showgrid=True, gridcolor="rgba(0,0,0,0.08)", zeroline=False),
        yaxis=dict(showgrid=False, tickfont=dict(size=12)),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(timeframe_str)


def _run_appearances_section():
    """Render the Appearances section: top 10 charts per league, top 5 combined, all leagues."""
    st.header("Appearances")
    st.subheader("Top 10 current players by appearances")
    with st.spinner("Loading appearances data…"):
        appearances, players, year_min, year_max, club_ids_per_league = load_appearances_data()

    if year_min is not None and year_max is not None:
        timeframe_str = f"Appearances between {year_min} and {year_max}. Data covers only this period; totals before or after are not included."
    else:
        timeframe_str = "Appearance dates could not be determined."

    # Per-league: only players still in that league (current club in league as of latest season / 2025)
    st.markdown("**Per league** — Only players who still play in that league (current squad in latest season). Appearances in that competition only.")
    comp_to_name = {
        "GB1": "Premier League",
        "ES1": "La Liga",
        "IT1": "Serie A",
        "L1": "Bundesliga",
        "FR1": "Ligue 1",
    }
    for league_id in TOP5_LEAGUES:
        league_name = comp_to_name[league_id]
        top10 = appearances_top10_in_league(
            league_id, league_name, appearances, players, club_ids_per_league.get(league_id, set())
        )
        _bar_chart_appearances(
            top10,
            f"Top 10 — {league_name}",
            timeframe_str,
        )

    st.divider()
    st.markdown("**Top 5 leagues combined** — Current players at a top‑5 club; total appearances in all competitions.")
    top10_top5 = appearances_top10_top5_leagues(appearances, players)
    _bar_chart_appearances(
        top10_top5,
        "Top 10 appearances — current players in the top 5 European leagues",
        timeframe_str,
    )

    st.divider()
    st.markdown("**All leagues** — Current players at any club; total appearances in all competitions.")
    top10_all = appearances_top10_all_leagues(appearances, players)
    _bar_chart_appearances(
        top10_all,
        "Top 10 appearances — current players (any league)",
        timeframe_str,
    )

    st.caption("Current players = players with a current club in the dataset. Per‑league charts only include players still in that league (latest season).")


# ---- Home formations: rolling 3-month average of top 8 ----

@st.cache_data
def load_home_formations_series(competition_id: str | None):
    """Use club_games (home) + games; domestic league only. Optionally filter by competition_id (league).
    competition_id=None: all domestic leagues; else e.g. GB1 for Premier League. Top 8 formations, rolling 3-month avg."""
    club_games = load_csv(DATA_DIR, "club_games")
    games = load_csv(DATA_DIR, "games")
    games["date"] = pd.to_datetime(games["date"], errors="coerce")
    games = games[games["competition_type"] == "domestic_league"]
    if competition_id is not None:
        games = games[games["competition_id"] == competition_id]
    home_games = club_games[club_games["hosting"].str.upper().eq("HOME")][["game_id"]].drop_duplicates()
    merged = home_games.merge(
        games[["game_id", "date", "home_club_formation"]].rename(columns={"home_club_formation": "formation"}),
        on="game_id",
        how="inner",
    )
    merged = merged.dropna(subset=["date", "formation"])
    merged["month"] = merged["date"].dt.to_period("M").apply(lambda p: p.to_timestamp())
    by_month_form = merged.groupby(["month", "formation"]).size().reset_index(name="count")
    top8_formations = by_month_form.groupby("formation")["count"].sum().nlargest(8).index.tolist()
    by_month_form = by_month_form[by_month_form["formation"].isin(top8_formations)]
    wide = by_month_form.pivot_table(index="month", columns="formation", values="count", aggfunc="sum", fill_value=0)
    wide = wide.reindex(columns=top8_formations, fill_value=0)
    roll = wide.rolling(3, min_periods=1).mean()
    roll = roll.reset_index()
    return pd.melt(roll, id_vars=["month"], value_name="rolling_avg", var_name="formation")


def _run_home_formations_section():
    """Time series: rolling 3-month average of the 8 most popular home formations; split by domestic league."""
    st.header("Home formations")
    st.subheader("Rolling 3-month average of the 8 most popular home-team formations")
    league_options = [
        ("All domestic leagues", None),
        ("Premier League", "GB1"),
        ("La Liga", "ES1"),
        ("Serie A", "IT1"),
        ("Bundesliga", "L1"),
        ("Ligue 1", "FR1"),
    ]
    league_label = st.sidebar.selectbox(
        "League (domestic only)",
        [x[0] for x in league_options],
        index=0,
        key="formations_league",
    )
    competition_id = next(x[1] for x in league_options if x[0] == league_label)
    with st.spinner("Loading formations data…"):
        df = load_home_formations_series(competition_id)
    if df.empty:
        st.info("No formation data available for this selection.")
        return
    title_suffix = f" — {league_label}" if league_label != "All domestic leagues" else " (all domestic leagues)"
    fig = px.line(
        df,
        x="month",
        y="rolling_avg",
        color="formation",
        labels={"rolling_avg": "Rolling 3-month average (games)", "month": "Date"},
        title="Home-team formations over time (top 8 by usage)" + title_suffix,
    )
    fig.update_layout(
        font=dict(family=CHART_FONT, size=13, color="#1a1a1a"),
        paper_bgcolor=CHART_BG,
        plot_bgcolor=CHART_BG,
        margin=CHART_MARGIN,
        title=dict(font=dict(size=18), x=0, xanchor="left"),
        xaxis=dict(showgrid=True, gridcolor="rgba(0,0,0,0.08)", zeroline=False),
        yaxis=dict(showgrid=True, gridcolor="rgba(0,0,0,0.08)", zeroline=False),
        legend_title="Formation",
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Domestic (non-cup) league games only. Data: club_games (home) + games. Rolling 3-month average.")


# ---- Top 10 longest current streak: not lost when scored ----

@st.cache_data
def load_scored_not_lost_streaks():
    """Top 10 longest current streak: scored and team did not lose. Domestic league only.
    Only includes players who scored and played at least one domestic league match in the latest year of data (excludes retired)."""
    appearances = load_csv(DATA_DIR, "appearances")
    games = load_csv(DATA_DIR, "games")
    games = games[games["competition_type"] == "domestic_league"]
    domestic_game_ids = set(games["game_id"])
    appearances = appearances[appearances["game_id"].isin(domestic_game_ids)]
    appearances["date"] = pd.to_datetime(appearances["date"], errors="coerce")
    appearances = appearances.dropna(subset=["date"])
    appearances["goals"] = pd.to_numeric(appearances["goals"], errors="coerce").fillna(0).astype(int)
    latest_year = appearances["date"].max().year
    # Players who played in latest year
    played_latest = set(appearances[appearances["date"].dt.year == latest_year]["player_id"].unique())
    # Players who scored in latest year (domestic league)
    scored_latest = set(
        appearances[(appearances["date"].dt.year == latest_year) & (appearances["goals"] > 0)]["player_id"].unique()
    )
    active_scorers = played_latest & scored_latest
    appearances_scored = appearances[appearances["goals"] > 0]
    appearances_scored = appearances_scored[appearances_scored["player_id"].isin(active_scorers)]
    if appearances_scored.empty:
        return pd.DataFrame()
    games = games[["game_id", "home_club_id", "away_club_id", "home_club_goals", "away_club_goals"]].copy()
    merged = appearances_scored[["player_id", "game_id", "date", "player_club_id", "player_name"]].merge(
        games, on="game_id", how="inner"
    )
    merged["player_club_id"] = merged["player_club_id"].astype(int)
    merged["home_club_id"] = merged["home_club_id"].astype(int)
    merged["team_goals"] = merged.apply(
        lambda r: r["home_club_goals"] if r["player_club_id"] == r["home_club_id"] else r["away_club_goals"],
        axis=1,
    )
    merged["opp_goals"] = merged.apply(
        lambda r: r["away_club_goals"] if r["player_club_id"] == r["home_club_id"] else r["home_club_goals"],
        axis=1,
    )
    merged["not_lost"] = merged["team_goals"] >= merged["opp_goals"]
    merged = merged.sort_values(["player_id", "date"], ascending=[True, False])
    streak_list = []
    for player_id, g in merged.groupby("player_id"):
        n = 0
        for _, row in g.iterrows():
            if row["not_lost"]:
                n += 1
            else:
                break
        if n > 0:
            streak_list.append({
                "player_id": player_id,
                "player_name": g["player_name"].iloc[0],
                "streak": n,
            })
    streaks = pd.DataFrame(streak_list)
    if streaks.empty:
        return pd.DataFrame()
    return streaks.nlargest(10, "streak")


def _run_scored_not_lost_streak_section():
    """Top 10 longest current streak of players who have not lost when they have scored."""
    st.header("Scored & not lost")
    st.subheader("Top 10 longest current streak (games with a goal and no defeat)")
    with st.spinner("Computing streaks…"):
        top10 = load_scored_not_lost_streaks()
    if top10.empty:
        st.info("No streak data available.")
        return
    display = top10[["player_name", "streak"]].rename(columns={"player_name": "Player", "streak": "Current streak"})
    st.dataframe(display, use_container_width=True, hide_index=True)
    st.caption("Domestic league matches only. Only players who scored and played in the latest year of data (active players). Streak = consecutive games (most recent first) with a goal and no defeat (win or draw).")


# Professional layout / typography (Athletic-inspired)
PRO_CSS = """
<style>
    /* Editorial, clean layout */
    .stApp { max-width: 1100px; margin: 0 auto; padding-top: 1.5rem; }
    h1, h2, h3 { font-family: Georgia, 'Times New Roman', serif !important; font-weight: 600; color: #1a1a1a; letter-spacing: -0.02em; }
    h1 { font-size: 1.85rem; border-bottom: 1px solid rgba(0,0,0,0.08); padding-bottom: 0.5rem; margin-bottom: 1rem; }
    .stMarkdown { font-family: 'Segoe UI', system-ui, sans-serif; }
    .stSidebar .stMarkdown { font-size: 0.95rem; }
    hr { margin: 2rem 0; border: none; border-top: 1px solid rgba(0,0,0,0.08); }
    [data-testid="stSidebar"] { border-right: 1px solid rgba(0,0,0,0.06); }
</style>
"""


def main():
    st.set_page_config(page_title="European Leagues — Squad value & Appearances", layout="wide", initial_sidebar_state="expanded")
    st.markdown(PRO_CSS, unsafe_allow_html=True)
    st.title("European Leagues")
    st.caption("Squad value & appearances · Top 5 leagues")

    # Top-level section
    section = st.sidebar.radio(
        "Section",
        ["Squad value", "Appearances", "Home formations", "Scored & not lost streak"],
        index=0,
        label_visibility="collapsed",
    )

    if section == "Appearances":
        _run_appearances_section()
        return
    if section == "Home formations":
        _run_home_formations_section()
        return
    if section == "Scored & not lost streak":
        _run_scored_not_lost_streak_section()
        return

    # ---- Squad value section ----
    data = load_data()
    clubs_top5 = data["clubs"]
    valuations = data["valuations"]
    players = data["players"]

    view = st.sidebar.radio("View", ["Summary by league", "Club detail"], index=0, key="squad_view")

    if view == "Summary by league":
        st.header("Squad value over time")
        st.markdown("All clubs in each top 5 league; one value per year (highest total in that year).")
        by_league = squad_value_by_league_over_time(clubs_top5, valuations)
        if by_league.empty:
            st.warning("No valuation data for top 5 league clubs in the selected period.")
        else:
            fig = px.line(
                by_league,
                x="date",
                y="squad_value_eur",
                color="league_name",
                labels={"squad_value_eur": "Total squad value (€)", "date": "Date"},
                title="Total squad value by league",
            )
            fig.update_layout(
                yaxis_tickformat=",.0f",
                legend_title="League",
                hovermode="x unified",
                font=dict(family=CHART_FONT, size=13, color="#1a1a1a"),
                paper_bgcolor=CHART_BG,
                plot_bgcolor=CHART_BG,
                margin=CHART_MARGIN,
                title=dict(font=dict(size=18), x=0, xanchor="left"),
                xaxis=dict(showgrid=True, gridcolor="rgba(0,0,0,0.08)", zeroline=False),
                yaxis=dict(showgrid=True, gridcolor="rgba(0,0,0,0.08)", zeroline=False),
            )
            st.plotly_chart(fig, use_container_width=True)
        st.caption("One value per year (highest total squad value in that year). The latest year is omitted if valuation data does not yet cover the full year (avoids a misleading drop).")

    else:
        st.header("Club detail")
        leagues = clubs_top5["league_name"].dropna().unique()
        leagues = sorted(leagues)
        league_sel = st.sidebar.selectbox("League", leagues, index=0)
        # Only clubs that are still in this league (most recent season in dataset)
        latest_season = pd.to_numeric(clubs_top5["last_season"], errors="coerce").max()
        clubs_in_league = clubs_top5[
            (clubs_top5["league_name"] == league_sel)
            & (pd.to_numeric(clubs_top5["last_season"], errors="coerce") == latest_season)
        ].sort_values("name")
        club_options = clubs_in_league["name"].tolist()
        club_ids_in_league = clubs_in_league.set_index("name")["club_id"].to_dict()
        if not club_options:
            st.warning("No clubs found for this league in the current season.")
            return
        club_name = st.sidebar.selectbox("Club", club_options, index=0)
        club_id = club_ids_in_league[club_name]

        st.subheader(club_name)
        tab1, tab2 = st.tabs(["Squad value over time", "Player values"])

        with tab1:
            club_ts = squad_value_by_club_over_time(club_id, valuations)
            if club_ts.empty:
                st.info("No historical valuation data for this club.")
            else:
                current_squad_value = float(club_ts["squad_value_eur"].iloc[-1])
                st.metric("Current squad value", format_eur(current_squad_value))
                fig = px.line(
                    club_ts,
                    x="date",
                    y="squad_value_eur",
                    labels={"squad_value_eur": "Squad value (€)", "date": "Date"},
                    title=f"{club_name} — Squad value over time (max per year)",
                )
                fig.update_traces(line=dict(color=CHART_BAR_COLOR, width=2))
                fig.update_layout(
                    yaxis_tickformat=",.0f",
                    hovermode="x unified",
                    font=dict(family=CHART_FONT, size=13, color="#1a1a1a"),
                    paper_bgcolor=CHART_BG,
                    plot_bgcolor=CHART_BG,
                    margin=CHART_MARGIN,
                    title=dict(font=dict(size=18), x=0, xanchor="left"),
                    xaxis=dict(showgrid=True, gridcolor="rgba(0,0,0,0.08)", zeroline=False),
                    yaxis=dict(showgrid=True, gridcolor="rgba(0,0,0,0.08)", zeroline=False),
                )
                st.plotly_chart(fig, use_container_width=True)
                st.caption("One value per year (highest total squad value in that year).")

        with tab2:
            # Only players who still play for this club (current_club_id = club_id); current market value
            squad = players[players["current_club_id"] == club_id].copy()
            if squad.empty:
                st.info("No player records for this club in the players file.")
            else:
                squad = squad.rename(columns={"market_value_in_eur": "value_eur"})
                display = squad[["name", "position", "value_eur"]].copy()
                display["value_eur"] = pd.to_numeric(display["value_eur"], errors="coerce")
                display = display.dropna(subset=["value_eur"]).sort_values(
                    "value_eur", ascending=False
                )
                display["Value"] = display["value_eur"].apply(format_eur)
                st.dataframe(
                    display[["name", "position", "Value"]].rename(
                        columns={"name": "Player", "position": "Position"}
                    ),
                    use_container_width=True,
                    hide_index=True,
                )
                total = display["value_eur"].sum()
                st.metric("Total squad value (current)", format_eur(total))
                st.caption("Current market value; only players still at the club.")

    return


if __name__ == "__main__":
    main()
