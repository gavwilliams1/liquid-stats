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
    """Squad value timeseries: total per league per date (only clubs in top 5 leagues)."""
    # Restrict valuations to clubs in our top-5 club set
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
    by_date_league = (
        v.groupby(["month", "league_id", "league_name"])
        .agg(squad_value_eur=("market_value_in_eur", "sum"))
        .reset_index()
    )
    by_date_league["date"] = by_date_league["month"].dt.to_timestamp()
    return by_date_league.drop(columns=["month"])


@st.cache_data
def squad_value_by_club_over_time(club_id, valuations):
    """Squad value timeseries for one club (from player_valuations where current_club_id = club_id)."""
    v = valuations[valuations["current_club_id"] == club_id].copy()
    v["month"] = v["date"].dt.to_period("M")
    v = (
        v.groupby("month")
        .agg(squad_value_eur=("market_value_in_eur", "sum"))
        .reset_index()
    )
    v["date"] = v["month"].dt.to_timestamp()
    return v.drop(columns=["month"])


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
    """Load appearances and players for the appearances section."""
    appearances = load_csv(DATA_DIR, "appearances")
    players = load_csv(DATA_DIR, "players")
    return appearances, players


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


def _bar_chart_appearances(df: pd.DataFrame, title: str, y_label: str = "Appearances") -> None:
    """Render a horizontal bar chart for appearance counts."""
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
    fig.update_traces(textposition="outside")
    fig.update_layout(yaxis_categoryorder="total ascending", showlegend=False, height=400)
    st.plotly_chart(fig, use_container_width=True)


def _run_appearances_section():
    """Render the Appearances section: top 10 charts per league, top 5 combined, all leagues."""
    st.header("Appearances — Top 10 current players by appearances")
    with st.spinner("Loading appearances data…"):
        appearances, players = load_appearances_data()

    # 1) One chart per top 5 league (appearances in that league only)
    st.subheader("Per league (appearances in that league)")
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
            f"Top 10 — {league_name} (current players, appearances in {league_name})",
        )

    st.divider()
    # 2) Top 10 among current players in top 5 leagues (total appearances)
    st.subheader("Top 5 leagues combined (total appearances)")
    top10_top5 = appearances_top10_top5_leagues(appearances, players)
    _bar_chart_appearances(
        top10_top5,
        "Top 10 appearances — current players in the top 5 European leagues (all competitions)",
    )

    st.divider()
    # 3) Top 10 among current players in any league (total appearances)
    st.subheader("All leagues (total appearances)")
    top10_all = appearances_top10_all_leagues(appearances, players)
    _bar_chart_appearances(
        top10_all,
        "Top 10 appearances — current players in any league (all competitions)",
    )

    st.caption("Current players = players with a current club in the dataset. Appearances are career totals in the relevant competition(s).")


def main():
    st.set_page_config(page_title="Squad value dashboard", layout="wide")
    st.title("Top 5 European leagues — Squad value & Appearances")

    # Top-level section: Squad value vs Appearances
    section = st.sidebar.radio("Section", ["Squad value", "Appearances"], index=0)

    if section == "Appearances":
        _run_appearances_section()
        return

    # ---- Squad value section ----
    data = load_data()
    clubs_top5 = data["clubs"]
    valuations = data["valuations"]
    players = data["players"]

    view = st.sidebar.radio("View", ["Summary by league", "Club detail"], index=0, key="squad_view")

    if view == "Summary by league":
        st.header("Squad value over time (all clubs, by league)")
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
                title="Total squad value by league over time",
            )
            fig.update_layout(
                yaxis_tickformat=",.0f",
                legend_title="League",
                hovermode="x unified",
            )
            st.plotly_chart(fig, use_container_width=True)
        st.caption("Data: player valuations aggregated by current club and league (top 5: Premier League, La Liga, Serie A, Bundesliga, Ligue 1).")

    else:
        st.header("Club detail")
        # League filter then club selector, sorted by league
        leagues = clubs_top5["league_name"].dropna().unique()
        leagues = sorted(leagues)
        league_sel = st.sidebar.selectbox("League", leagues, index=0)
        clubs_in_league = clubs_top5[clubs_top5["league_name"] == league_sel].sort_values(
            "name"
        )
        club_options = clubs_in_league["name"].tolist()
        club_ids_in_league = clubs_in_league.set_index("name")["club_id"].to_dict()
        if not club_options:
            st.warning("No clubs found for this league.")
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
                fig = px.line(
                    club_ts,
                    x="date",
                    y="squad_value_eur",
                    labels={"squad_value_eur": "Squad value (€)", "date": "Date"},
                    title=f"{club_name} — Squad value over time",
                )
                fig.update_layout(yaxis_tickformat=",.0f", hovermode="x unified")
                st.plotly_chart(fig, use_container_width=True)

        with tab2:
            # Current squad: players whose current_club_id is this club
            squad = players[players["current_club_id"] == club_id].copy()
            if squad.empty:
                st.info("No player records for this club in the players file.")
            else:
                # Use market_value_in_eur from players (current snapshot)
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

    return


if __name__ == "__main__":
    main()
