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

    # 4. Add jd_hash to analyses (DEFAULT '' for existing rows)
    try:
        cur.execute("ALTER TABLE analyses ADD COLUMN jd_hash TEXT NOT NULL DEFAULT ''")
        print("✓ Added jd_hash to analyses")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("- jd_hash already exists, skipping")
        else:
            raise

    # 5. Create index on jd_hash for efficient cache lookups
    cur.execute(
        "CREATE INDEX IF NOT EXISTS ix_analyses_jd_hash ON analyses (jd_hash)"
    )
    print("✓ Index ix_analyses_jd_hash ready")

    # 6. Add status to analyses (nullable, no default)
    try:
        cur.execute("ALTER TABLE analyses ADD COLUMN status TEXT")
        print("✓ Added status to analyses")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("- status already exists, skipping")
        else:
            raise

    # 7. Create discovery_runs table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS discovery_runs (
            id           TEXT PRIMARY KEY,
            source       TEXT NOT NULL,
            triggered_by TEXT NOT NULL DEFAULT 'manual',
            status       TEXT NOT NULL DEFAULT 'pending',
            started_at   TIMESTAMP NOT NULL,
            completed_at TIMESTAMP,
            jobs_found          INTEGER NOT NULL DEFAULT 0,
            jobs_passed_stage1  INTEGER NOT NULL DEFAULT 0,
            jobs_passed_stage2  INTEGER NOT NULL DEFAULT 0,
            jobs_scored         INTEGER NOT NULL DEFAULT 0
        )
    """)
    print("✓ discovery_runs table ready")

    # 8. Create jobs table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id               TEXT PRIMARY KEY,
            sources          TEXT NOT NULL DEFAULT '[]',
            source_id        TEXT NOT NULL DEFAULT '',
            source_url       TEXT NOT NULL DEFAULT '',
            title            TEXT NOT NULL DEFAULT '',
            company          TEXT NOT NULL DEFAULT '',
            location         TEXT,
            raw_text         TEXT NOT NULL,
            dedup_hash       TEXT NOT NULL UNIQUE,
            discovered_at    TIMESTAMP NOT NULL,
            state            TEXT NOT NULL DEFAULT 'discovered',
            relevance_score  INTEGER,
            matched_profiles TEXT NOT NULL DEFAULT '[]',
            discovery_run_id TEXT NOT NULL REFERENCES discovery_runs(id)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS ix_jobs_dedup_hash ON jobs (dedup_hash)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_jobs_state ON jobs (state)")
    print("✓ jobs table ready")

    # 9. Add job_id to analyses
    try:
        cur.execute("ALTER TABLE analyses ADD COLUMN job_id TEXT REFERENCES jobs(id)")
        print("✓ Added job_id to analyses")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("- job_id already exists, skipping")
        else:
            raise

    # 10. Add saved column to jobs
    try:
        cur.execute("ALTER TABLE jobs ADD COLUMN saved INTEGER NOT NULL DEFAULT 0")
        print("✓ Added saved to jobs")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("- saved already exists, skipping")
        else:
            raise

    # 11. Create users table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id              TEXT PRIMARY KEY,
            email           TEXT NOT NULL UNIQUE,
            hashed_password TEXT NOT NULL,
            is_active       INTEGER NOT NULL DEFAULT 1,
            is_admin        INTEGER NOT NULL DEFAULT 0,
            created_at      TIMESTAMP NOT NULL
        )
    """)
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email)")
    print("✓ users table ready")

    # 12. Create invite_tokens table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS invite_tokens (
            id          TEXT PRIMARY KEY,
            token       TEXT NOT NULL UNIQUE,
            email       TEXT,
            created_by  TEXT NOT NULL REFERENCES users(id),
            used_by     TEXT REFERENCES users(id),
            expires_at  TIMESTAMP NOT NULL,
            used_at     TIMESTAMP
        )
    """)
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_invite_tokens_token ON invite_tokens (token)")
    print("✓ invite_tokens table ready")

    # 13. Create saved_jobs table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS saved_jobs (
            user_id  TEXT NOT NULL REFERENCES users(id),
            job_id   TEXT NOT NULL REFERENCES jobs(id),
            saved_at TIMESTAMP NOT NULL,
            PRIMARY KEY (user_id, job_id)
        )
    """)
    print("✓ saved_jobs table ready")

    # 14. Add user_id to profiles
    try:
        cur.execute("ALTER TABLE profiles ADD COLUMN user_id TEXT REFERENCES users(id)")
        print("✓ Added user_id to profiles")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("- user_id on profiles already exists, skipping")
        else:
            raise

    # 15. Add user_id to analyses
    try:
        cur.execute("ALTER TABLE analyses ADD COLUMN user_id TEXT REFERENCES users(id)")
        print("✓ Added user_id to analyses")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("- user_id on analyses already exists, skipping")
        else:
            raise

    # 16. Create llm_calls table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS llm_calls (
            id            TEXT PRIMARY KEY,
            agent_name    TEXT NOT NULL,
            model         TEXT NOT NULL,
            input_tokens  INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            cost_usd      REAL NOT NULL DEFAULT 0.0,
            latency_ms    INTEGER NOT NULL DEFAULT 0,
            cache_hit     INTEGER NOT NULL DEFAULT 0,
            analysis_id   TEXT REFERENCES analyses(id),
            run_id        TEXT REFERENCES discovery_runs(id),
            created_at    TIMESTAMP NOT NULL
        )
    """)
    print("✓ llm_calls table ready")

    # 17. Create contacts table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id           TEXT PRIMARY KEY,
            analysis_id  TEXT NOT NULL REFERENCES analyses(id),
            email        TEXT NOT NULL,
            name         TEXT,
            title        TEXT,
            company      TEXT,
            source       TEXT NOT NULL DEFAULT 'hunter',
            confidence   REAL NOT NULL DEFAULT 0.0,
            status       TEXT NOT NULL DEFAULT 'discovered',
            draft_subject TEXT,
            draft_text   TEXT,
            sent_at      TIMESTAMP,
            created_at   TIMESTAMP NOT NULL
        )
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS ix_contacts_analysis_id ON contacts (analysis_id)"
    )
    print("✓ contacts table ready")

    # 18. Add cache_creation_tokens to llm_calls
    try:
        cur.execute(
            "ALTER TABLE llm_calls ADD COLUMN cache_creation_tokens INTEGER NOT NULL DEFAULT 0"
        )
        print("✓ Added cache_creation_tokens to llm_calls")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("- cache_creation_tokens already exists, skipping")
        else:
            raise

    # 19. Add cache_read_tokens to llm_calls
    try:
        cur.execute(
            "ALTER TABLE llm_calls ADD COLUMN cache_read_tokens INTEGER NOT NULL DEFAULT 0"
        )
        print("✓ Added cache_read_tokens to llm_calls")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("- cache_read_tokens already exists, skipping")
        else:
            raise

    conn.commit()
    conn.close()
    print("Migration complete.")


if __name__ == "__main__":
    main()
