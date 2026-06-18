"""Versioning parity with the platform: first-lock semver, snapshot pins
(genes + curated regions + reference versions), immutability, the conditional
unlock (allowed until a run consumes the version), and fork/clone."""

from app.models import PanelVersion


def _create(client, label, **kw):
    r = client.post("/panels", json={"label": label, "type": "DNA", **kw})
    assert r.status_code == 201, r.text
    return r.json()


def test_first_lock_is_1_0_0_and_snapshot_pins_everything(ctx):
    c = ctx.client
    pid = _create(c, "BRCA panel")["id"]
    assert c.post(f"/panels/{pid}/add-genes",
                  json={"symbols": ["BRCA1", "BRCA2"]}).status_code == 200
    assert c.post(f"/panels/{pid}/regions",
                  json={"chr": "chr17", "start": 43044295, "end": 43125483,
                        "name": "BRCA1 promoter", "kind": "promoter"}).status_code == 201
    assert c.post(f"/panels/{pid}/validate").json()["status"] == "validated"

    locked = c.post(f"/panels/{pid}/lock", json={"bump": "minor"})
    assert locked.status_code == 200, locked.text
    assert locked.json()["current_version"] == "1.0.0"      # first lock = 1.0.0

    hist = c.get(f"/panels/{pid}/history").json()
    assert len(hist) == 1
    assert hist[0]["version"] == "1.0.0"
    assert hist[0]["content_hash"].startswith("sha256:")    # platform format

    # the snapshot pins genes + curated regions + reference versions
    with ctx.Session() as s:
        snap = s.query(PanelVersion).one().snapshot
    assert snap["n_genes"] == 2
    assert len(snap["custom_regions"]) == 1
    assert snap["custom_regions"][0]["name"] == "BRCA1 promoter"
    assert snap["reference_versions"]["genome_build"] == "GRCh38"
    assert snap["reference_versions"]["mane_release"] == "1.5"

    # locked → immutable
    assert c.post(f"/panels/{pid}/add-genes",
                  json={"symbols": ["TP53"]}).status_code == 409


def test_validate_requires_a_gene(ctx):
    pid = _create(ctx.client, "empty panel")["id"]
    r = ctx.client.post(f"/panels/{pid}/validate")
    assert r.status_code == 422
    assert "no genes" in r.json()["error"]["detail"]


def test_no_op_relock_is_rejected(ctx):
    c = ctx.client
    pid = _create(c, "stable panel")["id"]
    c.post(f"/panels/{pid}/add-genes", json={"symbols": ["EGFR"]})
    c.post(f"/panels/{pid}/validate")
    assert c.post(f"/panels/{pid}/lock", json={"bump": "minor"}).status_code == 200
    # unlock then re-lock with identical content → same hash → 409
    assert c.post(f"/panels/{pid}/unlock", json={"reason": "test"}).status_code == 200
    c.post(f"/panels/{pid}/validate")
    again = c.post(f"/panels/{pid}/lock", json={"bump": "minor"})
    assert again.status_code == 409
    assert "unchanged" in again.json()["error"]["detail"]


def test_unlock_allowed_until_consumed(ctx):
    c = ctx.client
    pid = _create(c, "unlock panel")["id"]
    c.post(f"/panels/{pid}/add-genes", json={"symbols": ["KRAS"]})
    c.post(f"/panels/{pid}/validate")
    assert c.post(f"/panels/{pid}/lock", json={"bump": "minor"}).status_code == 200

    # un-consumed: a mistaken lock can be undone
    u = c.post(f"/panels/{pid}/unlock", json={"reason": "mistaken lock"})
    assert u.status_code == 200 and u.json()["status"] == "draft"

    # change content so the re-lock isn't a no-op, lock again, mark consumed
    c.post(f"/panels/{pid}/add-genes", json={"symbols": ["NRAS"]})
    c.post(f"/panels/{pid}/validate")
    assert c.post(f"/panels/{pid}/lock", json={"bump": "patch"}).status_code == 200
    latest = c.get(f"/panels/{pid}/history").json()[-1]
    assert c.post(f"/versions/{latest['id']}/mark-consumed",
                  json={"run_id": "run-1"}).status_code == 200

    # consumed: unlock is now forbidden → fork instead
    blocked = c.post(f"/panels/{pid}/unlock", json={"reason": "too late"})
    assert blocked.status_code == 409
    assert "fork" in blocked.json()["error"]["detail"]


def test_clone_copies_genes_and_regions(ctx):
    c = ctx.client
    src = _create(c, "source panel")["id"]
    c.post(f"/panels/{src}/add-genes", json={"symbols": ["BRCA1"]})
    c.post(f"/panels/{src}/regions",
           json={"chr": "chr1", "start": 100, "end": 200, "name": "r1"})

    clone = c.post("/panels", json={"label": "forked panel", "type": "DNA",
                                    "parent_id": src})
    assert clone.status_code == 201, clone.text
    cj = clone.json()
    assert cj["parent_id"] == src and cj["status"] == "draft"

    genes = c.get(f"/panels/{cj['id']}/genes").json()
    assert {g["symbol"] for g in genes} == {"BRCA1"}
    regions = c.get(f"/panels/{cj['id']}/regions").json()
    assert len(regions) == 1 and regions[0]["name"] == "r1"
