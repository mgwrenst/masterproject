# =============================================================================
# config.py — All settings for the text-to-query evaluation pipeline.
# Edit this file to change model, database, or scoring behaviour.
# =============================================================================

# ── LLM ──────────────────────────────────────────────────────────────────────
MODEL       = "gpt-4o-mini"   # OpenAI model to use
TEMPERATURE = 0.0             # 0 = deterministic (recommended for evaluation)
MAX_TOKENS  = 512

# ── MongoDB ───────────────────────────────────────────────────────────────────
MONGO_URI     = "mongodb://localhost:27017"
DATABASE_NAME = "groundtruth"   # ← change to your database name

# ── Scoring ───────────────────────────────────────────────────────────────────
# Document identity key used when comparing find/aggregate results.
# "_id" works for most collections. Change if your documents use a different key.
DOCUMENT_ID_KEY = "_id"

# Document precision threshold.
# 1.0 = generated result set must be a perfect superset of gold (no noise).
# 0.8 = up to 20% extra documents are tolerated as long as all gold docs are found.
# Override per run with --threshold on the command line.
DEFAULT_THRESHOLD = 1.0

# ── Paths ─────────────────────────────────────────────────────────────────────
RESULTS_DIR  = "results"
BENCHMARKS_DIR = "benchmarks"
SCHEMAS_DIR    = "schemas"