"""Idempotent seed of the known MCP substrate. Ported 1:1 from the platform's
`seed_mcp_servers` management command. `host == name` because on refgen-net the
compose service name IS the DNS hostname. Runs on startup; re-runnable."""

from __future__ import annotations

from .models import McpServer

# name, port, protocol, category, display_name, description
SERVERS = [
    ("db-mcp",     3016, "jsonrpc", "core",       "Database",            "SQLite backend — HGNC catalog, MANE Select, panels, audit."),
    ("r-mcp",      3001, "jsonrpc", "compute",    "R Analysis",          "R analysis — BSgenome + TxDb hg38."),
    ("py-mcp",     3003, "jsonrpc", "compute",    "Python Analysis",     "Python data analysis."),
    ("nf-mcp",     3004, "jsonrpc", "pipeline",   "Nextflow Pipelines",  "Nextflow runner — Picard, GATK, nf-core."),
    ("igv-mcp",    3005, "jsonrpc", "viz",        "IGV Genome Viewer",   "IGV embed + panel pies + gene tables."),
    ("hpo-mcp",    3006, "jsonrpc", "knowledge",  "HPO Phenotypes",      "HPO phenotype ↔ gene ↔ disease."),
    ("civic-mcp",  3007, "jsonrpc", "knowledge",  "CIViC Evidence",      "CIViC cancer clinical evidence."),
    ("clinvar-mcp",3008, "jsonrpc", "knowledge",  "ClinVar Variants",    "ClinVar SQLite cache."),
    ("vep-mcp",    3009, "jsonrpc", "annotation", "VEP Annotation",      "Ensembl VEP local cache, GRCh38."),
    ("gnomad-mcp", 3010, "jsonrpc", "knowledge",  "gnomAD Population",   "gnomAD allele frequencies."),
    ("acmg-mcp",   3011, "jsonrpc", "annotation", "ACMG Classification", "ACMG/AMP variant classification."),
    ("hugo-mcp",   3012, "jsonrpc", "knowledge",  "HGNC (online)",       "HGNC live lookup with cache."),
    ("ucsc-mcp",   3013, "jsonrpc", "knowledge",  "UCSC Genome Browser", "UCSC Genome Browser API."),
    ("pubmed-mcp", 3021, "jsonrpc", "knowledge",  "PubMed Literature",   "PubMed search via NCBI E-utilities."),
    ("excalidraw", 3014, "static",  "diagram",    "Excalidraw Canvas",   "Excalidraw drawing canvas UI."),
    ("mermaid",    3015, "static",  "diagram",    "Mermaid Studio",      "Mermaid diagram editor UI."),
]


def seed_servers(session_factory) -> int:
    """Upsert the known servers by name. Returns the number of rows touched."""
    db = session_factory()
    try:
        for name, port, protocol, category, display, desc in SERVERS:
            srv = db.query(McpServer).filter_by(name=name).first()
            if srv is None:
                db.add(McpServer(
                    name=name, host=name, port=port, protocol=protocol,
                    category=category, display_name=display, description=desc,
                    is_enabled=True,
                ))
            else:
                srv.host, srv.port, srv.protocol = name, port, protocol
                srv.category, srv.display_name, srv.description = category, display, desc
                srv.is_enabled = True
        db.commit()
        return len(SERVERS)
    finally:
        db.close()
