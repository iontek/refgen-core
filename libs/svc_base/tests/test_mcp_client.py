from svc_base.mcp_client import _normalize_tools, mcp_url


def test_mcp_url_default_and_env_override(monkeypatch):
    monkeypatch.delenv("NF_MCP_URL", raising=False)
    assert mcp_url("nf-mcp", 3004) == "http://nf-mcp:3004/"
    monkeypatch.setenv("NF_MCP_URL", "http://localhost:9999/")
    assert mcp_url("nf-mcp", 3004) == "http://localhost:9999/"


def test_normalize_tools_camelcase_and_dropping():
    raw = [
        {"name": "get_exons", "description": "exons", "inputSchema": {"type": "object"}},
        {"name": "", "description": "nameless — dropped"},
        {"name": "run_r_code"},   # missing desc/schema → defaults
    ]
    out = _normalize_tools(raw)
    assert [t["name"] for t in out] == ["get_exons", "run_r_code"]
    assert out[0]["input_schema"] == {"type": "object"}     # camelCase folded
    assert out[1]["description"] == "" and out[1]["input_schema"] == {}


def test_normalize_tools_handles_none():
    assert _normalize_tools(None) == []
