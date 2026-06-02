"""Season-level player ratings from box scores.

A rating is a property of the *player*, not the team (the whole roster-composition
idea): we aggregate every game a player logged this season regardless of which team
they suited up for. The metric is a transparent, box-score-only proxy — Hollinger's
**Game Score**, normalised per 36 minutes and league-centred so an average-rate
rotation player scores ~0. It is intentionally *not* Basketball-Reference BPM; true
BPM / EPM / RAPM are documented future swaps (see docs/methodology.md, SPEC ratings.metric).

Game Score (per game):
    GmSc = PTS + 0.4*FGM - 0.7*FGA - 0.4*(FTA-FTM)
           + 0.7*OREB + 0.3*DREB + STL + 0.7*AST + 0.7*BLK - 0.4*PF - TOV
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml


def game_score(df: pd.DataFrame) -> pd.Series:
    """Hollinger Game Score per row (box-score only)."""
    return (
        df["PTS"]
        + 0.4 * df["FGM"]
        - 0.7 * df["FGA"]
        - 0.4 * (df["FTA"] - df["FTM"])
        + 0.7 * df["OREB"]
        + 0.3 * df["DREB"]
        + df["STL"]
        + 0.7 * df["AST"]
        + 0.7 * df["BLK"]
        - 0.4 * df["PF"]
        - df["TOV"]
    )


def compute_player_ratings(
    boxscores: pd.DataFrame,
    season: str | None = None,
    per_minutes: int = 36,
    min_minutes: int = 200,
) -> pd.DataFrame:
    """Aggregate box scores into one rating row per player.

    Returns columns: player_id, player_name, season, games, minutes,
    gmsc_per{per_minutes}, box_rating, reliable.

    ``box_rating`` is league-centred: the minutes-weighted league mean is exactly 0,
    so it reads as "Game Score per {per_minutes} min above/below an average-rate player"
    — a value-over-average that is natural to minutes-weight when aggregating to teams.
    ``reliable`` flags players with enough minutes for the rating to be stable.
    """
    df = boxscores.copy()
    df["GMSC"] = game_score(df)

    agg = df.groupby(["PLAYER_ID", "PLAYER_NAME"], as_index=False).agg(
        games=("GAME_ID", "nunique"),
        minutes=("MIN", "sum"),
        gmsc_total=("GMSC", "sum"),
    )
    agg = agg[agg["minutes"] > 0].copy()

    gmsc_per_min = agg["gmsc_total"] / agg["minutes"]
    league_mean_per_min = agg["gmsc_total"].sum() / agg["minutes"].sum()

    ratings = pd.DataFrame(
        {
            "player_id": agg["PLAYER_ID"].astype(str),
            "player_name": agg["PLAYER_NAME"],
            "season": season,
            "games": agg["games"].astype(int),
            "minutes": agg["minutes"].astype(int),
            f"gmsc_per{per_minutes}": (gmsc_per_min * per_minutes).round(2),
            "box_rating": ((gmsc_per_min - league_mean_per_min) * per_minutes).round(2),
            "reliable": agg["minutes"] >= min_minutes,
        }
    )
    return ratings.sort_values("box_rating", ascending=False).reset_index(drop=True)


def main() -> None:
    params = yaml.safe_load(Path("params.yaml").read_text())
    season = params["ingest"]["season"]
    cfg = params.get("ratings", {})
    boxscores = pd.read_parquet(Path("data/raw/boxscores") / f"{season}.parquet")

    ratings = compute_player_ratings(
        boxscores,
        season=season,
        per_minutes=int(cfg.get("per_minutes", 36)),
        min_minutes=int(cfg.get("min_minutes", 200)),
    )
    out_path = Path("data/processed/player_ratings.parquet")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ratings.to_parquet(out_path, index=False)
    print(
        f"Wrote ratings for {len(ratings)} players "
        f"({int(ratings['reliable'].sum())} reliable, {season}) to {out_path}"
    )


if __name__ == "__main__":
    main()
