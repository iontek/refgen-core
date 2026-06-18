"""create-target-bed pipeline steps. Each (db, run, step, ctx) → result dict.
Heavy work is delegated to MCPs (db-mcp gene/exon, nf-mcp merge); panel genes/
regions come from panels-svc. ctx carries the workspace dir, a service token,
and inter-step state (resolved genes, file paths)."""

from __future__ import annotations

import json
import os

import httpx

from svc_base import mcp_client
from svc_base.versioning import reference_versions

from .config import settings

WORKSPACE = "/workspace"
DB_MCP = lambda: mcp_client.mcp_url("db-mcp", 3016)   # noqa: E731
NF_MCP = lambda: mcp_client.mcp_url("nf-mcp", 3004)   # noqa: E731


def _tool_result(base, tool, args, timeout=60):
    r = mcp_client.call_tool(base, tool, args, timeout=timeout)
    if isinstance(r, dict) and r.get("error"):
        raise RuntimeError(f"{tool}: {r['error']}")
    res = r.get("result", {}) if isinstance(r, dict) else {}
    if isinstance(res, dict):
        if "text" in res:
            return res["text"]
        content = res.get("content")
        if content and isinstance(content, list):
            return content[0].get("text", "")
    return ""


def _tool_json(base, tool, args, timeout=60):
    txt = _tool_result(base, tool, args, timeout=timeout)
    try:
        return json.loads(txt) if txt else {}
    except Exception:
        return {"_raw": txt}


def _panels_get(path, ctx, timeout=30):
    h = {"Authorization": f"Bearer {ctx['token']}"} if ctx.get("token") else {}
    r = httpx.get(f"{settings.panels_url}{path}", headers=h, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _mcp_version(base):
    try:
        d = httpx.get(base.rstrip("/") + "/version", timeout=5).json()
        return {"mcp_version": d.get("version"),
                "tools": {t["name"]: t.get("version")
                          for t in d.get("tools", []) if "name" in t}}
    except Exception as exc:  # noqa: BLE001
        return {"error": type(exc).__name__}


# ── steps ─────────────────────────────────────────────────────────────────────

def step_hgnc_validate(db, run, step, ctx):
    """Resolve the run's gene symbols against HGNC (db-mcp)."""
    if run.gene_symbol:
        symbols = [run.gene_symbol]
    elif run.panel_id:
        genes = _panels_get(f"/panels/{run.panel_id}/genes", ctx)
        symbols = [g["symbol"] for g in genes]
    else:
        raise RuntimeError("run has neither gene_symbol nor panel_id")
    if not symbols:
        raise RuntimeError("no genes to design")

    out = _tool_json(DB_MCP(), "gene_catalog_bulk_validate", {"symbols": symbols})
    results = out.get("results", [])
    resolved = [{"symbol": r.get("current_symbol") or r["submitted"], "hgnc_id": r["hgnc_id"]}
                for r in results if r.get("hgnc_id")]
    not_found = [r["submitted"] for r in results if not r.get("hgnc_id")]
    ctx["genes"] = resolved
    return {"genes_requested": len(symbols), "genes_resolved": len(resolved),
            "not_found": not_found}


def step_cds_extract(db, run, step, ctx):
    """MANE-CDS exon coords (db-mcp.mane_exons) → target.bed (0-based half-open)."""
    from .pipeline import save_artifact

    hgnc_ids = [g["hgnc_id"] for g in ctx.get("genes", []) if g.get("hgnc_id")]
    if not hgnc_ids:
        raise RuntimeError("no resolved genes for CDS extraction")
    cds_only = run.params.get("cds_only", True)
    out = _tool_json(DB_MCP(), "mane_exons", {
        "hgnc_ids": hgnc_ids, "cds_only": cds_only,
        "transcript_kind": run.params.get("transcript_mode", "mane_select"),
    })
    lines, n_genes = [], 0
    for g in out.get("results", []):
        n_genes += 1
        for e in g["exons"]:
            s, en = (e.get("cds_start"), e.get("cds_end")) if (cds_only and e.get("is_cds")) \
                else (e.get("exon_start"), e.get("exon_end"))
            if s is None or en is None:
                continue
            lines.append(f"{g['chr']}\t{int(s) - 1}\t{int(en)}\t{g['symbol']}_ex{e['exon_rank']}\t0\t{g['strand']}")
    path = os.path.join(ctx["ws"], "target.bed")
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + ("\n" if lines else ""))
    save_artifact(db, run, step, "target_bed", path)
    ctx["target_bed"] = path
    total_bp = sum(int(l.split("\t")[2]) - int(l.split("\t")[1]) for l in lines)
    return {"interval_count": len(lines), "total_bp": total_bp,
            "genes_with_intervals": n_genes}


def step_custom_regions(db, run, step, ctx):
    """Append the panel's curated regions (panels-svc) to target.bed."""
    regions = _panels_get(f"/panels/{run.panel_id}/regions", ctx) if run.panel_id else []
    if not regions:
        return {"added": 0}
    path = ctx.get("target_bed") or os.path.join(ctx["ws"], "target.bed")
    with open(path, "a") as fh:
        for r in regions:
            fh.write(f"{r['chr']}\t{int(r['start'])}\t{int(r['end'])}\t{r['name']}\t0\t.\n")
    return {"added": len(regions)}


def step_padding(db, run, step, ctx):
    """Uniform ±padding_bp (clamped at 0). Local — no MCP."""
    from .pipeline import save_artifact

    pad = int(run.params.get("padding_bp", 20))
    src = ctx.get("target_bed") or os.path.join(ctx["ws"], "target.bed")
    out = os.path.join(ctx["ws"], "target_padded.bed")
    n = 0
    with open(src) as fi, open(out, "w") as fo:
        for line in fi:
            line = line.rstrip("\n")
            if not line:
                continue
            f = line.split("\t")
            f[1], f[2] = str(max(0, int(f[1]) - pad)), str(int(f[2]) + pad)
            fo.write("\t".join(f) + "\n")
            n += 1
    save_artifact(db, run, step, "padded_bed", out)
    return {"intervals": n, "padding_bp": pad}


def _local_merge(src_path, out_path, d=0):
    """Pure-Python sort + merge of overlapping/adjacent intervals (the same
    interval algebra bedtools merge does). Fallback when nf-mcp lacks bedtools."""
    rows = []
    with open(src_path) as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            p = line.split("\t")
            rows.append((p[0], int(p[1]), int(p[2])))
    rows.sort(key=lambda r: (r[0], r[1]))
    merged = []
    for chrom, s, e in rows:
        if merged and merged[-1][0] == chrom and s <= merged[-1][2] + d:
            merged[-1] = (chrom, merged[-1][1], max(merged[-1][2], e))
        else:
            merged.append((chrom, s, e))
    with open(out_path, "w") as fh:
        for chrom, s, e in merged:
            fh.write(f"{chrom}\t{s}\t{e}\n")
    return len(rows), len(merged)


def step_merge(db, run, step, ctx):
    """sort + merge intervals. Delegates to nf-mcp (bedtools) when available;
    falls back to a local Python merge (trivial interval algebra) otherwise."""
    from .pipeline import save_artifact

    ws_rel = os.path.relpath(ctx["ws"], WORKSPACE)
    out_rel = os.path.join(ws_rel, "target_merged.bed")
    out_path = os.path.join(WORKSPACE, out_rel)
    src = os.path.join(ctx["ws"], "target_padded.bed")
    d = int(run.params.get("merge_distance", 0))

    method, nf_note = "nf-mcp", ""
    try:
        nf_note = _tool_result(NF_MCP(), "bed_merge", {
            "bed": os.path.join(ws_rel, "target_padded.bed"), "output": out_rel,
            "d": d, "sort_first": True}, timeout=120)
    except Exception as exc:  # noqa: BLE001
        nf_note = f"nf-mcp error: {type(exc).__name__}"
    if not (os.path.exists(out_path) and os.path.getsize(out_path) > 0):
        method = "local-fallback"          # nf-mcp unavailable / no bedtools
        _local_merge(src, out_path, d)
    if not os.path.exists(out_path):
        raise RuntimeError(f"merge produced no output (nf-mcp: {nf_note[:120]})")

    save_artifact(db, run, step, "merged_bed", out_path)
    return {"method": method, "nf_note": nf_note.strip()[:120],
            "intervals_after": sum(1 for _ in open(out_path))}


def step_summary(db, run, step, ctx):
    """Provenance manifest (schema refgen.provenance/1): panel version content_hash,
    params_hash, software (MCP versions), reference_versions, per-step chain with
    per-artifact sha256. This is the run-integrity record."""
    from .models import ProbeArtifact, ProbeRunStep
    from .pipeline import _ms, save_artifact

    steps = (db.query(ProbeRunStep).filter_by(run_id=run.id)
             .order_by(ProbeRunStep.step_order).all())
    artifacts = db.query(ProbeArtifact).filter_by(run_id=run.id).all()

    # panel version pin: look up the locked version's content_hash (proof anchor)
    panel_ver = None
    if run.panel_id and run.panel_version:
        try:
            hist = _panels_get(f"/panels/{run.panel_id}/history", ctx)
            match = next((v for v in hist if v.get("version") == run.panel_version), None)
            panel_ver = {"version": run.panel_version,
                         "content_hash": match.get("content_hash") if match else None}
        except Exception:
            panel_ver = {"version": run.panel_version}

    software = {"design-svc": settings.service_version,
                "db-mcp": _mcp_version(DB_MCP()), "nf-mcp": _mcp_version(NF_MCP())}

    chain = []
    for s in steps:
        if s.step_name == step.step_name:
            continue
        outs = [{"name": os.path.basename(a.path), "sha256": a.sha256,
                 "size_bytes": a.size_bytes} for a in artifacts if a.step_id == s.id]
        chain.append({"order": s.step_order, "step": s.step_name, "tool": s.tool_id,
                      "status": s.status, "metrics": s.result or {}, "outputs": outs,
                      "duration_ms": s.duration_ms})

    manifest = {
        "schema": "refgen.provenance/1", "run_id": run.id, "pipeline": run.pipeline_slug,
        "panel_id": run.panel_id, "panel_version": panel_ver, "gene_symbol": run.gene_symbol,
        "triggered_by": run.triggered_by, "created_at": _ms(run.created_at),
        "params": run.params, "params_hash": run.params_hash,
        "software": software, "reference_versions": reference_versions(),
        "chain": chain,
        "artifacts": [{"kind": a.kind, "path": os.path.basename(a.path),
                       "sha256": a.sha256, "size_bytes": a.size_bytes} for a in artifacts],
    }
    path = os.path.join(ctx["ws"], "manifest.json")
    with open(path, "w") as fh:
        json.dump(manifest, fh, indent=2, default=str)
    art = save_artifact(db, run, step, "manifest", path, mime="application/json")
    run.summary = {"chain_steps": len(chain), "artifact_count": len(artifacts) + 1,
                   "manifest_sha256": art.sha256}
    db.commit()
    return {"chain_steps": len(chain), "manifest_sha256": art.sha256}
