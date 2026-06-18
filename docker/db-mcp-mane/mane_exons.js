// mane_exons — read MANE exon coordinates (the gap that blocked dxm's
// create-target-bed). The data already lives in db-mcp's mane_exon table
// (204k rows); db-mcp just lacked a read tool. Follows the db-mcp tool
// convention (export TOOL + run; conn via _db.js). Returns CDS exon intervals
// per gene so design-svc can build target.bed (cds_start/cds_end where is_cds).
//
// args: { symbols?: [str], hgnc_ids?: [str], transcript_kind?="mane_select",
//         cds_only?=true }
import { db } from "./_db.js";

export const TOOL = { name: "mane_exons", version: "1.0.0" };

export function run(args) {
  const conn = db();
  const symbols = (args.symbols || []).map(s => String(s).trim().toUpperCase()).filter(Boolean);
  const hgncIds = (args.hgnc_ids || []).map(s => String(s).trim()).filter(Boolean);
  const kind = args.transcript_kind || "mane_select";
  const cdsOnly = args.cds_only !== false;          // default true
  if (symbols.length === 0 && hgncIds.length === 0)
    return { text: JSON.stringify({ error: "symbols or hgnc_ids required" }) };

  const where = [];
  const params = [];
  if (symbols.length) {
    where.push(`UPPER(symbol) IN (${symbols.map(() => "?").join(",")})`);
    params.push(...symbols);
  }
  if (hgncIds.length) {
    where.push(`hgnc_id IN (${hgncIds.map(() => "?").join(",")})`);
    params.push(...hgncIds);
  }
  let sql = `SELECT hgnc_id, symbol, transcript_id, transcript_kind, chr, strand,
                    exon_rank, exon_start, exon_end, cds_start, cds_end, is_cds
             FROM mane_exon
             WHERE (${where.join(" OR ")}) AND transcript_kind = ?`;
  params.push(kind);
  if (cdsOnly) sql += ` AND is_cds = 1`;
  sql += ` ORDER BY symbol, chr, exon_start`;

  const rows = conn.prepare(sql).all(...params);

  const genes = {};
  for (const r of rows) {
    const g = genes[r.symbol] || (genes[r.symbol] = {
      symbol: r.symbol, hgnc_id: r.hgnc_id, transcript_id: r.transcript_id,
      transcript_kind: r.transcript_kind, chr: r.chr, strand: r.strand, exons: [],
    });
    g.exons.push({
      exon_rank: r.exon_rank, exon_start: r.exon_start, exon_end: r.exon_end,
      cds_start: r.cds_start, cds_end: r.cds_end, is_cds: r.is_cds,
    });
  }
  const results = Object.values(genes);
  const found = new Set();
  for (const g of results) { found.add(g.symbol.toUpperCase()); found.add(g.hgnc_id); }
  const not_found = [...symbols, ...hgncIds].filter(q => !found.has(q));

  return { text: JSON.stringify({
    transcript_kind: kind, cds_only: cdsOnly,
    gene_count: results.length, results, not_found,
  }) };
}
