#!/usr/bin/env python3
"""Apply schema changes to an existing data/jobfit.db.

Safe to run multiple times — each step is idempotent.
"""
import sqlite3
from pathlib import Path


def main() -> None:
    db_path = Path("data/jobfit.db")
    if not db_path.exists():
        print(f"No database at {db_path} — nothing to migrate (init_db will create it fresh).")
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # 1. Add github_last_fetched_at to profiles (nullable, no default)
    try:
        cur.execute("ALTER TABLE profiles ADD COLUMN github_last_fetched_at TIMESTAMP")
        print("✓ Added github_last_fetched_at to profiles")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("- github_last_fetched_at already exists, skipping")
        else:
            raise

    # 2. Create github_cache table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS github_cache (
            id          TEXT PRIMARY KEY,
            owner       TEXT NOT NULL,
            repo_name   TEXT NOT NULL,
            readme_content TEXT NOT NULL DEFAULT '',
            fetched_at  TIMESTAMP NOT NULL,
            last_modified TEXT,
            UNIQUE(owner, repo_name)
        )
    """)
    print("✓ github_cache table ready")

    # 3. Add evaluate_only to analyses (DEFAULT 0 = complete, so existing rows treated as complete)
    try:
        cur.execute("ALTER TABLE analyses ADD COLUMN evaluate_only BOOLEAN NOT NULL DEFAULT 0")
        print("✓ Added evaluate_only to analyses")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("- evaluate_only already exists, skipping")
        else:
            raise

    conn.commit()
    conn.close()
    print("Migration complete.")


if __name__ == "__main__":
    main()
