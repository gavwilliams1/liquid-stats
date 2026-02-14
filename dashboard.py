"""
Squad value dashboard: top 5 European leagues.
All CSV data is loaded via load_csv() so that both single files and split
(_part1, _part2, ...) files are used, giving the latest data including 2026.
"""
import re
import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent
TOP5_LEAGUES = ("GB1", "ES1", "IT1", "L1", "FR1")  # Premier League, La Liga, Serie A, Bundesliga, Ligue 1


def load_csv(basedir: Path, name: str) -> pd.DataFrame:
    """Load a CSV by base name: uses name.csv if present, else name_part1.csv, name_part2.csv, ... (all parts concatenated). Ensures latest data from split files is included."""
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
    """Squad value by year: one value per year = highest total squad value in that year (per league). Excludes the latest year if data does not reach October to avoid a misleading drop."""
    club_ids = set(clubs_top5["club_id"])
    v = valuations[valuations["current_club_id"].isin(club_ids)].copy()
    v = v.merge(
        clubs_top5[["club_id", "league_id", "league_name"]],
        left_on="current_club_id",
        right_on="club_id",
        how="left",
    )
    v = v.dropna(subset=["league_id"])
    max_date = v["date"].max()
    if pd.notna(max_date) and max_date.month < 10:
        v = v[v["date"].dt.year < max_date.year]
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
    """Squad value by year for one club: one value per year = highest total in that year. Excludes latest year if data does not reach October to avoid a misleading drop."""
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


# Chart styling: mobile-friendly height, automatic width
CHART_FONT = "Georgia, 'Times New Roman', serif"
CHART_BAR_COLOR = "#c93434"
CHART_BG = "rgba(0,0,0,0)"
CHART_MARGIN = dict(t=50, b=45, l=50, r=20)
CHART_HEIGHT = 280  # Fits mobile; use_container_width=True handles width


# ---- Substitution minutes: relative frequency histogram (2025-26 domestic league) ----

SUBSTITUTION_SEASON = 2025  # 2025-26 season


@st.cache_data
def load_substitution_minutes(competition_id: str | None):
    """Minutes when substitutions occurred in 2025-26 domestic league games. competition_id None = all top 5 leagues."""
    game_events = load_csv(DATA_DIR, "game_events")
    games = load_csv(DATA_DIR, "games")
    games["season"] = pd.to_numeric(games["season"], errors="coerce")
    dom = games[
        (games["competition_type"] == "domestic_league")
        & (games["season"] == SUBSTITUTION_SEASON)
        & (games["competition_id"].isin(TOP5_LEAGUES))
    ]
    if competition_id is not None:
        dom = dom[dom["competition_id"] == competition_id]
    game_ids = set(dom["game_id"])
    subs = game_events[
        (game_events["type"].astype(str).str.strip().str.lower() == "substitutions")
        & (game_events["game_id"].isin(game_ids))
    ].copy()
    if subs.empty:
        return pd.Series(dtype=float)
    # Parse minute: can be int or "90+2" -> take first part as minute for binning
    def parse_minute(m):
        if pd.isna(m):
            return None
        s = str(m).strip()
        if "+" in s:
            s = s.split("+")[0].strip()
        return pd.to_numeric(s, errors="coerce")

    subs["minute_num"] = subs["minute"].apply(parse_minute)
    subs = subs.dropna(subset=["minute_num"])
    subs = subs[(subs["minute_num"] >= 0) & (subs["minute_num"] <= 120)]
    return subs["minute_num"]


def _run_substitution_minutes_section():
    """Relative frequency histogram of substitution minutes in 2025-26 domestic league; filter by top 5 league."""
    st.header("Substitution minutes")
    st.subheader("2025-26 domestic league — when substitutions are made")
    league_options = [
        ("All top 5 leagues", None),
        ("Premier League", "GB1"),
        ("La Liga", "ES1"),
        ("Serie A", "IT1"),
        ("Bundesliga", "L1"),
        ("Ligue 1", "FR1"),
    ]
    league_label = st.sidebar.selectbox(
        "League",
        [x[0] for x in league_options],
        index=0,
        key="sub_minutes_league",
    )
    competition_id = next(x[1] for x in league_options if x[0] == league_label)
    with st.spinner("Loading substitution data…"):
        minutes = load_substitution_minutes(competition_id)
    if minutes.empty or len(minutes) == 0:
        st.info("No substitution data for 2025-26 domestic league in this selection.")
        return
    title_suffix = f" — {league_label}" if league_label != "All top 5 leagues" else " (all top 5 leagues)"
    fig = px.histogram(
        x=minutes,
        nbins=min(91, int(minutes.max() - minutes.min() + 1) if minutes.max() > minutes.min() else 90),
        range_x=[0, 91],
        labels={"x": "Minute", "y": "Relative frequency"},
        title="Relative frequency of substitution minute" + title_suffix,
        histnorm="probability",
    )
    fig.update_traces(marker_color=CHART_BAR_COLOR)
    fig.update_layout(
        height=CHART_HEIGHT,
        autosize=True,
        showlegend=False,
        font=dict(family=CHART_FONT, size=13, color="#1a1a1a"),
        paper_bgcolor=CHART_BG,
        plot_bgcolor=CHART_BG,
        margin=CHART_MARGIN,
        title=dict(font=dict(size=18), x=0, xanchor="left"),
        xaxis=dict(showgrid=True, gridcolor="rgba(0,0,0,0.08)", zeroline=False, dtick=5),
        yaxis=dict(showgrid=True, gridcolor="rgba(0,0,0,0.08)", zeroline=False, tickformat=".1%"),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Data: game_events (Substitutions) in domestic league matches, 2025-26 season. Y-axis = proportion of all substitutions in that league(s).")


# ---- Home formations: rolling 3-month average of top 8 ----

@st.cache_data
def load_home_formations_series(competition_id: str | None):
    """Use club_games (home) + games; domestic league only. Top 8 formations: proportion of all matches in each month, then rolling 3-month average of proportion."""
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
    total_per_month = merged.groupby("month").size()
    by_month_form["total_in_month"] = by_month_form["month"].map(total_per_month)
    by_month_form["proportion"] = by_month_form["count"] / by_month_form["total_in_month"].replace(0, pd.NA)
    top8_formations = by_month_form.groupby("formation")["count"].sum().nlargest(8).index.tolist()
    by_month_form = by_month_form[by_month_form["formation"].isin(top8_formations)].dropna(subset=["proportion"])
    wide = by_month_form.pivot_table(index="month", columns="formation", values="proportion", aggfunc="sum", fill_value=0)
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
        labels={"rolling_avg": "Rolling 3-month average (share of matches)", "month": "Date"},
        title="Home-team formations over time (top 8 by usage)" + title_suffix,
    )
    fig.update_layout(
        height=CHART_HEIGHT,
        autosize=True,
        font=dict(family=CHART_FONT, size=13, color="#1a1a1a"),
        paper_bgcolor=CHART_BG,
        plot_bgcolor=CHART_BG,
        margin=CHART_MARGIN,
        title=dict(font=dict(size=18), x=0, xanchor="left"),
        xaxis=dict(showgrid=True, gridcolor="rgba(0,0,0,0.08)", zeroline=False),
        yaxis=dict(showgrid=True, gridcolor="rgba(0,0,0,0.08)", zeroline=False, tickformat=".0%"),
        legend_title="Formation",
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Domestic (non-cup) league games only. Proportion of all matches in each month using that formation; rolling 3-month average of proportion.")


# ---- Top 10 longest current streak: not lost when scored ----

# Scored & not lost: only players who played and scored in a domestic league match on or after this date
STREAK_ACTIVE_CUTOFF = pd.Timestamp("2025-08-01")  # August 2025


@st.cache_data
def load_scored_not_lost_streaks():
    """Top 10 longest current streak: scored and team did not lose. Domestic league only. Active = played and scored in a match on or after August 2025. Data loaded via load_csv (includes split files)."""
    appearances = load_csv(DATA_DIR, "appearances")
    games = load_csv(DATA_DIR, "games")
    games = games[games["competition_type"] == "domestic_league"]
    domestic_game_ids = set(games["game_id"])
    appearances = appearances[appearances["game_id"].isin(domestic_game_ids)]
    appearances["date"] = pd.to_datetime(appearances["date"], errors="coerce")
    appearances = appearances.dropna(subset=["date"])
    appearances["goals"] = pd.to_numeric(appearances["goals"], errors="coerce").fillna(0).astype(int)
    # Players who played on or after August 2025
    played_cutoff = set(appearances[appearances["date"] >= STREAK_ACTIVE_CUTOFF]["player_id"].unique())
    # Players who scored on or after August 2025 (domestic league)
    scored_cutoff = set(
        appearances[(appearances["date"] >= STREAK_ACTIVE_CUTOFF) & (appearances["goals"] > 0)]["player_id"].unique()
    )
    active_scorers = played_cutoff & scored_cutoff
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
    # Latest match = most recent game in which they scored (domestic league) on or after August 2025
    latest_scored_after_cutoff = merged[merged["date"] >= STREAK_ACTIVE_CUTOFF].groupby("player_id")["date"].max()
    streak_list = []
    for player_id, g in merged.groupby("player_id"):
        n = 0
        streak_start = None
        for _, row in g.iterrows():
            if row["not_lost"]:
                n += 1
                streak_start = row["date"]
            else:
                break
        if n > 0 and streak_start is not None:
            # Latest match = most recent scored game after Aug 2025 (not necessarily the start of the streak)
            streak_latest = latest_scored_after_cutoff.get(player_id)
            if streak_latest is None:
                continue  # should not happen for active_scorers
            streak_list.append({
                "player_id": player_id,
                "player_name": g["player_name"].iloc[0],
                "streak": n,
                "streak_start": streak_start,
                "streak_latest": streak_latest,
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
    top10["position"] = range(1, len(top10) + 1)
    top10["streak_start_str"] = pd.to_datetime(top10["streak_start"]).dt.strftime("%Y-%m-%d")
    top10["streak_latest_str"] = pd.to_datetime(top10["streak_latest"]).dt.strftime("%Y-%m-%d")
    display = top10[["position", "player_name", "streak", "streak_start_str", "streak_latest_str"]].rename(
        columns={
            "position": "Rank",
            "player_name": "Player",
            "streak": "Current streak",
            "streak_start_str": "Streak started",
            "streak_latest_str": "Latest match (scored, not lost)",
        }
    )
    st.dataframe(display, use_container_width=True, hide_index=True)
    st.caption("Domestic league matches only. Only players who scored and played in at least one match on or after August 2025. Streak = consecutive games (most recent first) with a goal and no defeat (win or draw).")


# Mobile-first layout: native iPhone app feel, automatic width, safe areas
PRO_CSS = """
<style>
    /* Full viewport, safe-area insets for notch/home indicator (iOS) */
    .stApp {
        max-width: 100%;
        width: 100%;
        margin: 0;
        padding: max(1rem, env(safe-area-inset-top)) max(1rem, env(safe-area-inset-right)) max(1.5rem, env(safe-area-inset-bottom)) max(1rem, env(safe-area-inset-left));
        padding-top: max(1rem, env(safe-area-inset-top));
        box-sizing: border-box;
        -webkit-text-size-adjust: 100%;
    }
    @media (min-width: 641px) {
        .stApp { max-width: 1100px; margin: 0 auto; padding-left: 1.5rem; padding-right: 1.5rem; }
    }
    /* Charts and blocks: full width on mobile */
    [data-testid="stVerticalBlock"] > div { width: 100% !important; max-width: 100% !important; }
    [data-testid="stPlotlyChart"] { width: 100% !important; max-width: 100% !important; }
    /* Typography */
    h1, h2, h3 { font-family: Georgia, 'Times New Roman', serif !important; font-weight: 600; color: #1a1a1a; letter-spacing: -0.02em; }
    h1 { font-size: clamp(1.35rem, 5vw, 1.85rem); border-bottom: 1px solid rgba(0,0,0,0.08); padding-bottom: 0.5rem; margin-bottom: 1rem; }
    h2 { font-size: clamp(1.15rem, 4vw, 1.4rem); }
    .stMarkdown { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif; }
    .stSidebar .stMarkdown { font-size: 0.95rem; }
    hr { margin: 1.5rem 0; border: none; border-top: 1px solid rgba(0,0,0,0.08); }
    /* Sidebar: card-like on mobile when expanded */
    [data-testid="stSidebar"] {
        border-right: 1px solid rgba(0,0,0,0.06);
        padding-right: env(safe-area-inset-right);
    }
    /* Metrics and dataframes: responsive */
    [data-testid="stMetric"] { padding: 0.5rem 0; }
    .stDataFrame { overflow-x: auto; -webkit-overflow-scrolling: touch; }
</style>
"""


def main():
    st.set_page_config(page_title="European Leagues — Squad value & Appearances", layout="wide", initial_sidebar_state="expanded")
    st.markdown(PRO_CSS, unsafe_allow_html=True)
    st.title("European Leagues")
    st.caption("Squad value & more · Top 5 leagues")

    # Top-level section
    section = st.sidebar.radio(
        "Section",
        ["Player and squad value", "Substitution minutes", "Home formations", "Scored & not lost streak"],
        index=0,
        label_visibility="collapsed",
    )

    if section == "Substitution minutes":
        _run_substitution_minutes_section()
        return
    if section == "Home formations":
        _run_home_formations_section()
        return
    if section == "Scored & not lost streak":
        _run_scored_not_lost_streak_section()
        return

    # ---- Player and squad value section ----
    data = load_data()
    clubs_top5 = data["clubs"]
    valuations = data["valuations"]
    players = data["players"]

    view = st.sidebar.radio(
        "View",
        ["Summary by league", "Club detail", "Most valuable players by league"],
        index=0,
        key="squad_view",
    )

    if view == "Summary by league":
        st.header("Squad value over time")
        st.markdown("All clubs in each top 5 league; one value per year (highest total in that year).")
        by_league = squad_value_by_league_over_time(clubs_top5, valuations)
        if by_league.empty:
            st.warning("No valuation data for top 5 league clubs in the selected period.")
        else:
            by_league = by_league.copy()
            by_league["squad_value_m"] = (by_league["squad_value_eur"] / 1e6).round(1)
            fig = px.line(
                by_league,
                x="date",
                y="squad_value_m",
                color="league_name",
                labels={"squad_value_m": "Total squad value (€M)", "date": "Date"},
                title="Total squad value by league",
            )
            fig.update_layout(
                height=CHART_HEIGHT,
                autosize=True,
                yaxis_tickformat=",.1f",
                yaxis_ticksuffix="M",
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
            fig.update_traces(hovertemplate="€%{y:,.1f}M<extra></extra>")
            st.plotly_chart(fig, use_container_width=True)
        st.caption("One value per year (highest total squad value in that year). The latest year is omitted if valuation data does not reach October, to avoid a misleading drop.")

    elif view == "Most valuable players by league":
        st.header("Most valuable players by league")
        st.markdown("Current market value; players in each top 5 league, sorted by value (top 15 per league). Valuation date = latest valuation date in player_valuations.")
        comp_to_name = {"GB1": "Premier League", "ES1": "La Liga", "IT1": "Serie A", "L1": "Bundesliga", "FR1": "Ligue 1"}
        players["value_eur"] = pd.to_numeric(players["market_value_in_eur"], errors="coerce")
        players_with_value = players.dropna(subset=["value_eur"]).copy()
        latest_valuation_date = valuations.groupby("player_id")["date"].max().reset_index().rename(columns={"date": "valuation_date"})
        for league_id in TOP5_LEAGUES:
            league_name = comp_to_name[league_id]
            in_league = players_with_value[
                players_with_value["current_club_domestic_competition_id"].fillna("").eq(league_id)
            ]
            top = in_league.nlargest(15, "value_eur")[["player_id", "name", "position", "value_eur"]].copy()
            top = top.merge(latest_valuation_date, on="player_id", how="left")
            top["Value"] = top["value_eur"].apply(format_eur)
            top["Valuation date"] = pd.to_datetime(top["valuation_date"], errors="coerce").dt.strftime("%Y-%m-%d")
            top = top.rename(columns={"name": "Player", "position": "Position"})[["Player", "Position", "Value", "Valuation date"]]
            st.subheader(league_name)
            st.dataframe(top, use_container_width=True, hide_index=True)
        st.caption("Source: players (current club and market value); valuation date from player_valuations (latest per player). Top 15 per league.")

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
                club_ts = club_ts.copy()
                club_ts["squad_value_m"] = (club_ts["squad_value_eur"] / 1e6).round(1)
                fig = px.line(
                    club_ts,
                    x="date",
                    y="squad_value_m",
                    labels={"squad_value_m": "Squad value (€M)", "date": "Date"},
                    title=f"{club_name} — Squad value over time (max per year)",
                )
                fig.update_traces(line=dict(color=CHART_BAR_COLOR, width=2), hovertemplate="€%{y:,.1f}M<extra></extra>")
                fig.update_layout(
                    height=CHART_HEIGHT,
                    autosize=True,
                    yaxis_tickformat=",.1f",
                    yaxis_ticksuffix="M",
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
                st.caption("One value per year (highest total squad value in that year). Latest year omitted if data does not reach October.")

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
