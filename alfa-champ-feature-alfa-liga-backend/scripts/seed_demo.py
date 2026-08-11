from __future__ import annotations

from app.config import Settings
from app.db import Database
from app.fixtures import seed_demo_data


def main() -> None:
    settings = Settings()
    db = Database(settings.database_url)
    db.create_schema()
    with db.session_factory() as session:
        seed_demo_data(session)
    db.dispose()
    print("PASS: coffee_demo fixture and Alfa product catalog are ready")


if __name__ == "__main__":
    main()
