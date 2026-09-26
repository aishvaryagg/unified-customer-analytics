"""Settings, read from environment variables (optionally via a .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    gcp_project: str | None = None
    bq_dataset: str = "marketing_analytics"
    bq_location: str = "US"
    bq_max_bytes_billed: int = 50_000_000_000
    ga4_source_table: str = "bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*"
    ga4_start_date: str = "20201101"  # YYYYMMDD, inclusive
    ga4_end_date: str = "20210131"  # YYYYMMDD, inclusive; also the churn reference date
    churn_days: int = 30
    trend_threshold: float = 0.10
    mind_variant: str = "small"  # "small" (50k users) or "large" (1M users)
    mind_data_dir: str = "data/mind"
    mind_disengaged_days: int = 2
    mind_min_clicks: int = 3
    mind_drift_threshold: float = 0.20

    @property
    def ga4_end_date_iso(self) -> str:
        d = self.ga4_end_date
        return f"{d[:4]}-{d[4:6]}-{d[6:]}"

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        env = os.environ
        default = cls()
        return cls(
            gcp_project=env.get("GCP_PROJECT") or None,
            bq_dataset=env.get("BQ_DATASET", default.bq_dataset),
            bq_location=env.get("BQ_LOCATION", default.bq_location),
            bq_max_bytes_billed=int(env.get("BQ_MAX_BYTES_BILLED", default.bq_max_bytes_billed)),
            ga4_source_table=env.get("GA4_SOURCE_TABLE", default.ga4_source_table),
            ga4_start_date=env.get("GA4_START_DATE", default.ga4_start_date),
            ga4_end_date=env.get("GA4_END_DATE", default.ga4_end_date),
            churn_days=int(env.get("CHURN_DAYS", default.churn_days)),
            trend_threshold=float(env.get("TREND_THRESHOLD", default.trend_threshold)),
            mind_variant=env.get("MIND_VARIANT", default.mind_variant),
            mind_data_dir=env.get("MIND_DATA_DIR", default.mind_data_dir),
            mind_disengaged_days=int(env.get("MIND_DISENGAGED_DAYS", default.mind_disengaged_days)),
            mind_min_clicks=int(env.get("MIND_MIN_CLICKS", default.mind_min_clicks)),
            mind_drift_threshold=float(env.get("MIND_DRIFT_THRESHOLD", default.mind_drift_threshold)),
        )
