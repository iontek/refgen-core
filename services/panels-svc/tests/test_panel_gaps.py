"""Stage-1 panels gaps: compare (symbol set algebra), with-gene (reverse
lookup), members (project access control)."""


def _new(c, label, genes):
    pid = c.post("/panels", json={"label": label, "type": "DNA"}).json()["id"]
    if genes:
        c.post(f"/panels/{pid}/add-genes", json={"symbols": genes})
    return pid


def test_compare_set_algebra(ctx):
    c = ctx.client
    a = _new(c, "Panel A", ["BRCA1", "BRCA2", "TP53"])
    b = _new(c, "Panel B", ["BRCA1", "EGFR"])
    d = c.get(f"/panels/compare?ids={a},{b}").json()
    assert d["shared"] == ["BRCA1"]
    assert set(d["union"]) == {"BRCA1", "BRCA2", "TP53", "EGFR"}
    assert set(d["only"][a]) == {"BRCA2", "TP53"}
    assert d["only"][b] == ["EGFR"]
    assert len(d["panels"]) == 2


def test_compare_needs_two_panels(ctx):
    a = _new(ctx.client, "Solo", ["BRCA1"])
    assert ctx.client.get(f"/panels/compare?ids={a}").status_code == 400


def test_with_gene_reverse_lookup(ctx):
    c = ctx.client
    a = _new(c, "Has BRCA1", ["BRCA1", "TP53"])
    b = _new(c, "Also BRCA1", ["BRCA1"])
    _new(c, "No BRCA1", ["EGFR"])
    d = c.get("/panels/with-gene?symbols=brca1,UNKNOWN").json()   # case-insensitive
    ids = {p["id"] for p in d["BRCA1"]["panels"]}
    assert {a, b} <= ids
    assert d["UNKNOWN"]["panels"] == []


def test_members_lifecycle(ctx):
    c = ctx.client
    pid = _new(c, "Project X", ["BRCA1"])

    r = c.post(f"/panels/{pid}/members", json={"username": "alice", "role": "owner"})
    assert r.status_code == 201 and r.json()["role"] == "owner"

    # idempotent re-add updates the role (alice → designer)
    r2 = c.post(f"/panels/{pid}/members", json={"username": "alice", "role": "designer"})
    assert r2.status_code == 200 and r2.json()["role"] == "designer"

    # bad role rejected
    assert c.post(f"/panels/{pid}/members",
                  json={"username": "bob", "role": "king"}).status_code == 400

    # carol is now the only owner
    c.post(f"/panels/{pid}/members", json={"username": "carol", "role": "owner"})
    members = c.get(f"/panels/{pid}/members").json()
    assert len(members) == 2

    carol = next(m for m in members if m["username"] == "carol")
    assert c.delete(f"/panels/{pid}/members/{carol['id']}").status_code == 400  # last owner

    alice = next(m for m in members if m["username"] == "alice")
    assert c.delete(f"/panels/{pid}/members/{alice['id']}").status_code == 204
