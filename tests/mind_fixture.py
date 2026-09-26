"""A tiny MIND sample, written as real headerless TSV files, with known answers.

Articles: N1, N2 sports | N3, N5 finance (N5 has no abstract) | N4 health | N6 lifestyle.
N99 appears in an impression but is missing from news.tsv.
The data ends at 2019-11-15 23:00 (U3's dev impression).

U1  history N1 N2 N3 (sports 2/3, finance 1/3)
    11/9  09:00  clicks N3                  -> 1 click   Baseline
    11/10 10:00  clicks N5, N3              -> 2 clicks  Engagement expansion (+100%)
    11/14 20:00  clicks nothing (N99 shown) -> 0 clicks  Engagement contraction
    now reads only finance: drifting away from sports.  Passive (no click for 5+ days)
U2  no history; two impressions on 11/9 (1 click each) -> one active day, Insufficient history
U3  history N4
    11/11 07:00  clicks N4, N6              -> 2 clicks  Baseline
    11/15 23:00  clicks N6 (dev split, impression_id 1 again) -> 1 click, contraction; Engaged
U4  history N6
    11/9  08:00  clicks N6; 11/10 08:00 clicks N3 -> Flat; nothing after -> Disengaged
"""

from pathlib import Path

NEWS = [
    ("N1", "sports", "football_nfl", "Rookie quarterback leads comeback", "A late drive wins it.", "https://example.com/n1", "[]", "[]"),
    ("N2", "sports", "basketball_nba", "Star guard signs extension", "A four-year deal.", "https://example.com/n2", "[]", "[]"),
    ("N3", "finance", "markets", "Stocks rally on rate hopes", "Investors cheer.", "https://example.com/n3", "[]", "[]"),
    ("N4", "health", "wellness", "Five habits for better sleep", "Small changes help.", "https://example.com/n4", "[]", "[]"),
    ("N5", "finance", "personalfinance", "How to build an emergency fund", "", "https://example.com/n5", "[]", "[]"),
    ("N6", "lifestyle", "lifestyleroyals", "Holiday gift guide", "Ideas for everyone.", "https://example.com/n6", "[]", "[]"),
]

TRAIN_BEHAVIORS = [
    ("1", "U1", "11/9/2019 9:00:00 AM", "N1 N2 N3", "N3-1 N4-0 N1-0"),
    ("2", "U1", "11/10/2019 10:00:00 AM", "N1 N2 N3", "N5-1 N3-1 N6-0"),
    ("3", "U1", "11/14/2019 8:00:00 PM", "N1 N2 N3", "N4-0 N1-0 N99-0"),
    ("4", "U2", "11/9/2019 1:00:00 PM", "", "N1-1 N2-0"),
    ("5", "U2", "11/9/2019 3:00:00 PM", "", "N2-1"),
    ("6", "U3", "11/11/2019 7:00:00 AM", "N4", "N4-1 N6-1"),
    ("8", "U4", "11/9/2019 8:00:00 AM", "N6", "N6-1"),
    ("9", "U4", "11/10/2019 8:00:00 AM", "N6", "N6-0 N3-1"),
]

DEV_BEHAVIORS = [
    ("1", "U3", "11/15/2019 11:00:00 PM", "N4", "N6-1"),
]


def _write(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join("\t".join(r) + "\n" for r in rows), encoding="utf-8")


def write(data_dir: Path) -> Path:
    """Write the sample in MIND's layout: <data_dir>/<split>/{news,behaviors}.tsv."""
    _write(data_dir / "train" / "news.tsv", NEWS[:5])
    _write(data_dir / "dev" / "news.tsv", NEWS[3:])  # overlaps train, like the real files
    _write(data_dir / "train" / "behaviors.tsv", TRAIN_BEHAVIORS)
    _write(data_dir / "dev" / "behaviors.tsv", DEV_BEHAVIORS)
    return data_dir
