import argparse
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

import requests

from utils import ensure_dir, raw_activity_dir, write_json


BASE_URL = "https://intervals.icu/api/v1"
RAW_DIR = raw_activity_dir("intervals")
STATE_PATH = os.path.join("data", "backfill_state_intervals.json")


def _get_api_key() -> str:
    api_key = os.environ.get("INTERVALS_ICU_API_KEY", "").strip()

    if not api_key:
        raise RuntimeError(
            "INTERVALS_ICU_API_KEY environment variable is not set"
        )

    return api_key


def _get_activities(oldest: str, newest: str) -> List[Dict[str, Any]]:
    url = f"{BASE_URL}/athlete/0/activities"

    response = requests.get(
        url,
        params={
            "oldest": oldest,
            "newest": newest,
        },
        auth=("API_KEY", _get_api_key()),
        timeout=60,
    )

    response.raise_for_status()

    payload = response.json()

    if not isinstance(payload, list):
        raise RuntimeError(
            "Unexpected response from Intervals.icu activities endpoint"
        )

    return [
        item
        for item in payload
        if isinstance(item, dict)
    ]


def sync_intervals(
    dry_run: bool = False,
    prune_deleted: bool = False,
) -> Dict[str, Any]:

    # For the first implementation, use the configured sync start date.
    # If none exists, use the configured lookback period.
    from utils import load_config

    config = load_config()
    sync_config = config.get("sync", {}) or {}

    start_date = sync_config.get("start_date")

    if not start_date:
        lookback_years = int(
            sync_config.get("lookback_years", 5)
        )

        start_year = (
            datetime.now(timezone.utc).year
            - lookback_years
        )

        start_date = f"{start_year}-01-01"

    newest = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    print(
        f"Fetching Intervals.icu activities "
        f"from {start_date} to {newest}"
    )

    activities = _get_activities(
        oldest=start_date,
        newest=newest,
    )

    print(
        f"Intervals.icu returned {len(activities)} activities"
    )

    if dry_run:
        return {
            "source": "intervals",
            "activities": len(activities),
            "dry_run": True,
        }

    ensure_dir(RAW_DIR)
    ensure_dir("data")

    written = 0

    for activity in activities:
        activity_id = str(
            activity.get("id") or ""
        ).strip()

        if not activity_id:
            continue

        path = os.path.join(
            RAW_DIR,
            f"{activity_id}.json",
        )

        write_json(path, activity)
        written += 1

    state = {
        "source": "intervals",
        "oldest": start_date,
        "newest": newest,
        "updated_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "activity_count": written,
    }

    write_json(STATE_PATH, state)

    return {
        "source": "intervals",
        "activities": written,
        "dry_run": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync activities from Intervals.icu"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
    )

    parser.add_argument(
        "--prune-deleted",
        action="store_true",
    )

    args = parser.parse_args()

    result = sync_intervals(
        dry_run=args.dry_run,
        prune_deleted=args.prune_deleted,
    )

    print(result)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())