# db-mcp + mane_exons read tool, as a thin OVERLAY on the released image.
# We do NOT rebuild db-mcp from source (that re-resolves npm deps and risks the
# MCP rebuild-fragility) — we only drop one extra tool file into the existing,
# known-good image. The Node MCP base auto-loads every non-underscore *.js in
# server/tools/, so the new tool registers on next start.
#
#   docker build -f docker/db-mcp-mane/Dockerfile -t refgen/db-mcp:mane docker/db-mcp-mane
FROM ghcr.io/refgen/db-mcp:1.0.0
COPY mane_exons.js /app/server/tools/mane_exons.js
