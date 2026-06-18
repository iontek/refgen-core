"""registry-svc: seeded catalog, detail, status aggregation, tools/list sync."""

from svc_base import mcp_client

from app.seed import seed_servers


def test_seed_lists_all_servers(ctx):
    servers = ctx.client.get("/registry/mcp-servers").json()
    assert len(servers) == 16
    names = {s["name"] for s in servers}
    assert {"db-mcp", "nf-mcp", "r-mcp", "pubmed-mcp"} <= names
    db = next(s for s in servers if s["name"] == "db-mcp")
    assert db["port"] == 3016
    assert db["category"] == "core"
    assert db["base_url"] == "http://db-mcp:3016"
    assert db["tool_count"] == 0


def test_detail_by_name_and_id(ctx):
    by_name = ctx.client.get("/registry/mcp-servers/nf-mcp")
    assert by_name.status_code == 200
    body = by_name.json()
    assert body["tools"] == []
    # also resolvable by stable id
    assert ctx.client.get(f"/registry/mcp-servers/{body['id']}").status_code == 200
    assert ctx.client.get("/registry/mcp-servers/nope").status_code == 404


def test_seed_is_idempotent(ctx):
    seed_servers(ctx.Session)            # re-run
    assert len(ctx.client.get("/registry/mcp-servers").json()) == 16


def test_status_all_down_when_unreachable(ctx):
    # no MCPs reachable from the test container → every server probes down
    body = ctx.client.get("/mcp-status").json()
    assert body["summary"]["total"] == 16
    assert body["summary"]["down"] == 16
    assert body["cached"] is False


def test_sync_discovers_and_upserts_tools(ctx, monkeypatch):
    def fake_list_tools(base_url, **kw):
        if "nf-mcp" in base_url:
            return [
                {"name": "run_workflow", "description": "run", "input_schema": {}},
                {"name": "run_picard", "description": "picard", "input_schema": {}},
            ]
        raise RuntimeError("unreachable")

    monkeypatch.setattr(mcp_client, "list_tools", fake_list_tools)
    body = ctx.client.post("/registry/sync").json()
    assert body["synced"] == 1                       # only nf-mcp returned tools
    nf = next(r for r in body["results"] if r["name"] == "nf-mcp")
    assert nf["tools"] == 2 and nf["error"] is None
    # static servers are skipped, not errored
    mer = next(r for r in body["results"] if r["name"] == "mermaid")
    assert "static" in mer["error"]

    detail = ctx.client.get("/registry/mcp-servers/nf-mcp").json()
    assert {t["name"] for t in detail["tools"]} == {"run_workflow", "run_picard"}
    assert detail["tool_count"] == 2
