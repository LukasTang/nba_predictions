"""Pull raw player game logs for a season (the observable ground truth).

``LeagueGameLog`` (player level) returns one row per player-game for the whole season
in a single request, including ``TEAM_ABBREVIATION`` and ``GAME_DATE``. This is the
immutable historical record we derive transaction events from downstream — no look-ahead,
exact dates.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml
from nba_api.stats.endpoints import leaguegamelog


def pull_boxscores(season: str, timeout: int = 60) -> pd.DataFrame:
    resp = leaguegamelog.LeagueGameLog(
        player_or_team_abbreviation="P", season=season, timeout=timeout
    )
    return resp.get_data_frames()[0]


def main() -> None:
    params = yaml.safe_load(Path("params.yaml").read_text())
    season = params["ingest"]["season"]
    out_dir = Path("data/raw/boxscores")
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pull_boxscores(season)
    out_path = out_dir / f"{season}.parquet"
    df.to_parquet(out_path, index=False)
    print(
        f"Wrote {len(df)} player-game rows "
        f"({df['PLAYER_ID'].nunique()} players, {season}) to {out_path}"
    )


if __name__ == "__main__":
    main()
