from __future__ import annotations

import argparse
from pathlib import Path

from app.config import Settings
from app.db import Database
from app.services.experiments import ExperimentService
from app.services.products import ProductGateway


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export anonymized Alfa-Liga replay rows as JSONL."
    )
    parser.add_argument("--database-url", help="Override DATABASE_URL")
    parser.add_argument("--output", type=Path, help="Write JSONL to this path; stdout by default")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = Settings(**({"database_url": args.database_url} if args.database_url else {}))
    db = Database(settings.database_url)
    service = ExperimentService(ProductGateway(settings))
    with db.session_factory() as session:
        content = service.export_replay_jsonl(session)
    db.dispose()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
        print(f"Exported replay to {args.output}")
    else:
        print(content, end="")


if __name__ == "__main__":
    main()
