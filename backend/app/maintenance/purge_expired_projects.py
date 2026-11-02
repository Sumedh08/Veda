"""Preview or apply due project retention purges for a scheduled deployment job."""

import argparse

from app.db import SessionLocal
from app.maintenance.retention import count_expired_projects, purge_expired_projects


def _batch_size(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("batch size must be an integer") from exc
    if not 1 <= parsed <= 1000:
        raise argparse.ArgumentTypeError("batch size must be between 1 and 1000")
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="permanently delete expired archived project records; default is preview only",
    )
    parser.add_argument("--batch-size", type=_batch_size, default=100)
    args = parser.parse_args()

    with SessionLocal() as db:
        if args.apply:
            deleted = purge_expired_projects(db, batch_size=args.batch_size)
            print(f"Permanently deleted {deleted} expired archived project(s).")
        else:
            due = count_expired_projects(db)
            print(f"Dry run: {due} expired archived project(s) are eligible for purge.")


if __name__ == "__main__":
    main()
