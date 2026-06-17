"""ETL: migrate users from the old platform (auth_users in SQLite) into
identity-svc Postgres.

Django password hashes are kept AS-IS — identity-svc's verify_password
understands the Django pbkdf2_sha256 format, so users keep their passwords.
Idempotent: skips usernames that already exist.

Run via:  make migrate-users
"""

import os
import sqlite3

import psycopg2

OLD_DB = os.environ.get("OLD_DB", "/workspace/db/refgen.db")
PG_URL = os.environ["DATABASE_URL"]            # postgresql://...@.../identity
TENANT = os.environ.get("TENANT", "refgen")


def main():
    src = sqlite3.connect(OLD_DB)
    src.row_factory = sqlite3.Row
    dst = psycopg2.connect(PG_URL)
    cur = dst.cursor()

    added = skipped = 0
    for u in src.execute(
        "SELECT username,password,email,role,display_name,is_active FROM auth_users"
    ):
        cur.execute("SELECT 1 FROM users WHERE username=%s", (u["username"],))
        if cur.fetchone():
            skipped += 1
            continue
        cur.execute(
            """INSERT INTO users
               (username,password_hash,role,display_name,email,is_active,tenant_id)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (u["username"], u["password"], u["role"] or "designer",
             u["display_name"], u["email"], bool(u["is_active"]), TENANT),
        )
        added += 1

    dst.commit()
    print(f"users: +{added} added, {skipped} skipped (already present)")


if __name__ == "__main__":
    main()
