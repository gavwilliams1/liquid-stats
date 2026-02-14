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
    """Squad value by year: one value per year = highest total squad value in that year (per league)."""
    club_ids = set(clubs_top5["club_id"])
    v = valuations[valuations["current_club_id"].isin(club_ids)].copy()
    v = v.merge(
        clubs_top5[["club_id", "league_id", "league_name"]],
        left_on="current_club_id",
        right_on="club_id",
        how="left",
    )
    v = v.dropna(subset=["league_id"])
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
    """Squad value by year for one club: one value per year = highest total in that year."""
    v = valuations[valuations["current_club_id"] == club_id].copy()
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
    """Load appearances and players; compute min/max year for timeframe."""
    appearances = load_csv(DATA_DIR, "appearances")
    players = load_csv(DATA_DIR, "players")
    appearances["_date"] = pd.to_datetime(appearances["date"], errors="coerce")
    valid = appearances["_date"].dropna()
    year_min = int(valid.min().year) if len(valid) else None
    year_max = int(valid.max().year) if len(valid) else None
    appearances = appearances.drop(columns=["_date"])
    return appearances, players, year_min, year_max


@st.cache_data
def appearances_top10_in_league(league_id: str, league_name: str, appearances: pd.DataFrame, players: pd.DataFrame) -> pd.DataFrame:
    """Top 10 current players in this league by appearances in this league."""
    current_in_league = players[
        players["current_club_domestic_competition_id"].fillna("").eq(league_id)
        & players["current_club_id"].notna()
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
        appearances, players, year_min, year_max = load_appearances_data()

    if year_min is not None and year_max is not None:
        timeframe_str = f"Appearances between {year_min} and {year_max}. Data covers only this period; totals before or after are not included."
    else:
        timeframe_str = "Appearance dates could not be determined."

    # Per-league: only players who *currently* play in that league (current_club_domestic_competition_id)
    st.markdown("**Per league** — Only players who still play in that league. Appearances counted in that competition only.")
    comp_to_name = {
        "GB1": "Premier League",
        "ES1": "La Liga",
        "IT1": "Serie A",
        "L1": "Bundesliga",
        "FR1": "Ligue 1",
    }
    for league_id in TOP5_LEAGUES:
        league_name = comp_to_name[league_id]
        top10 = appearances_top10_in_league(league_id, league_name, appearances, players)
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

    st.caption("Current players = players with a current club in the dataset. Per‑league charts exclude players who have since moved to another league.")


# ---- Arsenal won the league at White Hart Lane 2004 ----

@st.cache_data
def load_arsenal_2004_match():
    """Try to find the Arsenal title-clinching match at White Hart Lane (25 Apr 2004) in games data."""
    try:
        games = load_csv(DATA_DIR, "games")
    except FileNotFoundError:
        return None
    games["date"] = pd.to_datetime(games["date"], errors="coerce")
    gb1 = games[games["competition_id"] == "GB1"]
    # Season 2003 = 2003/04; match was 25 April 2004
    g = gb1[
        (gb1["date"].dt.year == 2004)
        & (
            (gb1["home_club_name"].str.contains("Tottenham", case=False, na=False))
            & (gb1["away_club_name"].str.contains("Arsenal", case=False, na=False))
        )
    ]
    if len(g) == 0:
        return None
    return g.iloc[0].to_dict()


def _run_arsenal_2004_section():
    """Dedicated section: Arsenal won the Premier League at White Hart Lane, 2004."""
    st.header("Arsenal won the league at White Hart Lane")
    st.subheader("25 April 2004")

    match = load_arsenal_2004_match()

    if match:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Home", match.get("home_club_name", "—"))
        with col2:
            score = f"{match.get('home_club_goals', '')} – {match.get('away_club_goals', '')}"
            st.metric("Score", score)
        with col3:
            st.metric("Away", match.get("away_club_name", "—"))
        st.markdown(f"**Stadium:** {match.get('stadium', 'White Hart Lane')}  \n**Attendance:** {match.get('attendance', '—')}  \n**Referee:** {match.get('referee', '—')}")
        date_str = pd.to_datetime(match.get("date")).strftime("%d %B %Y") if match.get("date") else "25 April 2004"
        st.caption(f"Match data from dataset · {date_str}")
    else:
        st.markdown(
            """
            **Tottenham Hotspur 2–2 Arsenal**  
            *Premier League 2003/04*

            Arsenal clinched the Premier League title at the home of their north London rivals. 
            A 2–2 draw at White Hart Lane on **25 April 2004** gave the Invincibles an unassailable lead; 
            they would finish the season unbeaten (26 wins, 12 draws).

            *Match-level data in this dataset starts from 2013, so this fixture is not in the games file. 
            The summary above is from the historic record.*
            """
        )
        st.divider()
        st.markdown("**Stadium:** White Hart Lane  \n**Date:** 25 April 2004  \n**Competition:** Premier League (GB1)")


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

    # Top-level section: Squad value, Appearances, or Arsenal 2004
    section = st.sidebar.radio(
        "Section",
        ["Squad value", "Appearances", "Arsenal 2004"],
        index=0,
        label_visibility="collapsed",
    )

    if section == "Appearances":
        _run_appearances_section()
        return
    if section == "Arsenal 2004":
        _run_arsenal_2004_section()
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
        st.caption("One value per year (highest total squad value in that year). Player valuations aggregated by current club and league.")

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
