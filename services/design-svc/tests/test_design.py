"""design-svc Phase 1: recipe/adapter catalog + thin MCP passthrough."""

from svc_base import mcp_client


def test_builtin_recipes_seeded(ctx):
    body = ctx.client.get("/probe-design/runs/recipes").json()
    names = {r["name"] for r in body["recipes"]}
    assert {"default", "cgp-bait", "cgp-stringent", "hcs-dna"} <= names
    # default & hcs-dna share identical knobs but get distinct hashes (name in hash)
    hashes = {r["name"]: r["content_hash"] for r in body["recipes"]}
    assert hashes["default"] != hashes["hcs-dna"]
    assert all(h.startswith("sha256:") for h in hashes.values())


def test_create_recipe_and_dupe(ctx):
    spec = {"molecule": "DNA", "target": {"padding_bp": 30},
            "design": {"bait_size": 120}}
    r = ctx.client.post("/probe-design/runs/recipes",
                        json={"name": "mine", "version": "0.1.0", "spec": spec})
    assert r.status_code == 201, r.text
    assert r.json()["content_hash"].startswith("sha256:")
    # same name+version → 409
    dupe = ctx.client.post("/probe-design/runs/recipes",
                           json={"name": "mine", "version": "0.1.0", "spec": spec})
    assert dupe.status_code == 409


def test_adapter_crud(ctx):
    r = ctx.client.post("/probe-design/adapter-sets",
                        json={"name": "twist-v1", "platform": "twist_dna",
                              "adapter_5p": "ACGT", "adapter_3p": "TTAA"})
    assert r.status_code == 201, r.text
    assert r.json()["content_hash"].startswith("sha256:")
    assert len(ctx.client.get("/probe-design/adapter-sets").json()) == 1
    dupe = ctx.client.post("/probe-design/adapter-sets",
                           json={"name": "twist-v1", "platform": "twist_dna"})
    assert dupe.status_code == 409


def test_runs_empty_in_phase1(ctx):
    assert ctx.client.get("/probe-design/runs").json() == []


def test_lit_whitelist_rejects_unknown(ctx):
    r = ctx.client.post("/probe-design/lit", json={"tool": "rm_rf", "args": {}})
    assert r.status_code == 400


def test_passthrough_502_when_mcp_unreachable(ctx):
    # no MCP reachable from the test container → clean 502 (not a 500)
    r = ctx.client.get("/probe-design/clinvar/BRCA1")
    assert r.status_code == 502


def test_clinvar_passthrough_shape(ctx, monkeypatch):
    def fake_call_tool(base_url, name, arguments=None, **kw):
        assert "clinvar-mcp" in base_url and name == "clinvar_summary"
        assert arguments == {"gene": "BRCA1"}
        return {"result": {"text": "BRCA1: 1200 pathogenic variants"}}

    monkeypatch.setattr(mcp_client, "call_tool", fake_call_tool)
    r = ctx.client.get("/probe-design/clinvar/BRCA1")
    assert r.status_code == 200
    assert r.json()["gene"] == "BRCA1"
    assert "BRCA1" in r.json()["summary"]


def test_agents_passthrough_shape(ctx, monkeypatch):
    def fake_call_tool(base_url, name, arguments=None, **kw):
        assert "agent-mcp" in base_url and name == "list_agents"
        return {"result": {"agents": ["analyst", "oligo-assistant"]}}

    monkeypatch.setattr(mcp_client, "call_tool", fake_call_tool)
    r = ctx.client.get("/probe-design/agents")
    assert r.status_code == 200
    assert "analyst" in r.json()["agents"]
