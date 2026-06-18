"""ETL: migrate panels from the old platform SQLite into panels-svc Postgres.

Lossless transform (not a copy): maps the rich old schema, keeps the legacy id
as `code`, PRESERVES the original content_hash, stamps everything with a tenant.
Idempotent guard: aborts if migrated rows (code set) already exist.

Run via:  make migrate-panels   (mounts the old volume + reaches dxm postgres)
"""

import json
import os
import sqlite3
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import Json

OLD_DB = os.environ.get("OLD_DB", "/workspace/db/refgen.db")
PG_URL = os.environ["DATABASE_URL"]            # postgresql://user:pw@host/db
TENANT = os.environ.get("TENANT", "refgen")


def dt(v):
    """Old epoch int -> tz-aware datetime (handles seconds or milliseconds)."""
    if not v:
        return None
    v = int(v)
    secs = v / 1000 if v > 10 ** 11 else v
    return datetime.fromtimestamp(secs, tz=timezone.utc)


def main():
    src = sqlite3.connect(OLD_DB)
    src.row_factory = sqlite3.Row
    dst = psycopg2.connect(PG_URL)
    cur = dst.cursor()

    cur.execute("SELECT count(*) FROM panels WHERE code IS NOT NULL")
    already = cur.fetchone()[0]
    if already:
        print(f"ABORT: {already} migrated panels already present (code set). "
              "Clear them first if you want to re-run.")
        return

    now = datetime.now(timezone.utc)
    idmap = {}                                  # old code -> new int id

    for p in src.execute("SELECT * FROM panels ORDER BY created_at"):
        cur.execute(
            """INSERT INTO panels
               (code,label,ptype,status,details,sub_a,sub_b,parent_id,deadline,
                current_version,created_by,archived_at,created_at,updated_at,tenant_id)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (p["id"], p["label"], p["type"], p["status"], p["details"],
             p["sub_a"], p["sub_b"], p["parent_id"], dt(p["deadline"]),
             p["current_version"], p["created_by"], dt(p["archived_at"]),
             dt(p["created_at"]) or now, dt(p["updated_at"]) or now, TENANT),
        )
        idmap[p["id"]] = cur.fetchone()[0]
    print(f"panels:         {len(idmap)}")

    genes = 0
    for r in src.execute("SELECT * FROM panel_genes"):
        npid = idmap.get(r["panel_id"])
        if npid is None:
            continue
        cur.execute(
            """INSERT INTO panel_genes
               (panel_id,symbol,hgnc_id,target,transcript_override,notes,added_by,added_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (npid, r["symbol_at_add"], r["hgnc_id"], r["target"],
             r["transcript_override"], r["notes"], r["added_by"],
             dt(r["added_at"]) or now),
        )
        genes += 1
    print(f"panel_genes:    {genes}")

    versions = 0
    for r in src.execute("SELECT * FROM panel_versions"):
        npid = idmap.get(r["panel_id"])
        if npid is None:
            continue
        raw = r["snapshot_json"]
        try:
            snap = json.loads(raw) if raw else {}
        except Exception:
            snap = {"_raw": raw}
        cur.execute(
            """INSERT INTO panel_versions
               (panel_id,version,content_hash,parent_hash,bump_kind,status,snapshot,
                bait_files_path,lock_file_path,note,locked_by,signed_off_by,
                created_at,locked_at,tenant_id)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (npid, r["semver"], r["content_hash"], r["parent_hash"],
             r["bump_kind"], r["status"], Json(snap), r["bait_files_path"],
             r["lock_file_path"], r["note"], r["locked_by"], r["signed_off_by"],
             dt(r["created_at"]) or now, dt(r["locked_at"]), TENANT),
        )
        versions += 1
    print(f"panel_versions: {versions}")

    regions = 0
    try:
        src_regions = src.execute("SELECT * FROM panel_custom_regions")
    except sqlite3.OperationalError:
        src_regions = []                        # old DB predates curated regions
    for r in src_regions:
        npid = idmap.get(r["panel_id"])
        if npid is None:
            continue
        cur.execute(
            """INSERT INTO panel_custom_regions
               (panel_id,chr,start,"end",name,kind,hgvs,note,added_by,added_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (npid, r["chr"], r["start"], r["end"], r["name"], r["kind"],
             r["hgvs"], r["note"], r["added_by"], dt(r["added_at"]) or now),
        )
        regions += 1
    print(f"custom_regions: {regions}")

    dst.commit()
    print("committed.")


if __name__ == "__main__":
    main()
