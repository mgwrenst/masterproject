# =============================================================================
# pipeline.py — Text-to-query evaluation pipeline.
#
# Sections:
#   1. Imports & setup
#   2. Loading         — schema and benchmark files
#   3. LLM             — prompt construction and query generation
#   4. Database        — query execution against MongoDB
#   5. Scoring         — precision, recall, F1
#   6. Evaluation      — per-question orchestration
#   7. Results         — aggregation and saving
# =============================================================================


# ── 1. Imports & setup ────────────────────────────────────────────────────────

import json
import re
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv
from openai import OpenAI
from pymongo import MongoClient

import config

load_dotenv()

_openai_client = OpenAI()
_mongo_client: MongoClient | None = None

def _mongo(database: str | None):
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = MongoClient(config.MONGO_URI)
    return _mongo_client[database or config.DATABASE_NAME]


# ── 2. Loading ────────────────────────────────────────────────────────────────

def load_schema(path: str) -> str:
    """Read a YAML schema file and return it as a plain text string for the LLM prompt."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return yaml.dump(data, default_flow_style=False, allow_unicode=True)


def load_benchmark(path: str) -> list[dict]:
    """Read a JSON benchmark file containing questions and gold queries."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── 3. LLM ────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are an expert at translating natural language questions into MongoDB queries.

Given a database schema and a question, return ONLY a valid JSON object describing
the MongoDB operation to perform. Choose the most appropriate operation type.

Supported operations:

  find      — retrieve documents, optionally filtered and projected
  { "op": "find", "collection": "<name>", "filter": {...}, "projection": {...} }
  - omit projection unless specific fields are requested
  - use {"_id": 0} to hide the internal id when not needed

  distinct  — get unique values of a single field
  { "op": "distinct", "collection": "<name>", "field": "<fieldName>", "filter": {} }
  - use when the question asks for "all types", "unique values", or "distinct X"

  aggregate — grouping, counting, sorting, or multi-stage logic
  { "op": "aggregate", "collection": "<name>", "pipeline": [...] }
  - use when the question asks for counts, averages, or "per group" results

Rules:
- Return ONLY the JSON object — no explanation, no markdown, no code fences.
- Use exact field names from the schema.
- For nested fields, use dot notation (e.g. "address.city").
- An empty filter is written as {}.
"""

def generate_query(schema_text: str, question: str) -> dict:
    """
    Ask the LLM to generate a MongoDB query object for the given question.

    Returns:
        { "query": dict | None, "error": str | None }
    """
    prompt = f"Database schema:\n{schema_text}\n\nQuestion: {question}\n\nMongoDB query:"

    try:
        response = _openai_client.chat.completions.create(
            model=config.MODEL,
            temperature=config.TEMPERATURE,
            max_tokens=config.MAX_TOKENS,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
        )
        raw = response.choices[0].message.content or ""
        raw = raw.strip()

        # Strip markdown code fences if the model adds them despite instructions
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw).strip()
        return {"query": json.loads(cleaned), "error": None}

    except json.JSONDecodeError as e:
        return {"query": None, "error": f"JSON parse error: {e}"}
    except Exception as e:
        return {"query": None, "error": f"LLM error: {e}"}


# ── 4. Database ───────────────────────────────────────────────────────────────

def run_query(query: dict, database: str | None = None) -> dict:
    """
    Execute a query dict against MongoDB.

    Supported ops and required fields:
        find      — filter, projection (optional)
        distinct  — field, filter (optional)
        aggregate — pipeline

    Returns:
        { "results": list, "error": str | None }
    """
    try:
        col = _mongo(database)[query["collection"]]
        op  = query.get("op", "find")

        if op == "find":
            proj    = query.get("projection")
            cursor  = col.find(query.get("filter", {}), proj) if proj else col.find(query.get("filter", {}))
            results = list(cursor)
            _stringify_ids(results)

        elif op == "distinct":
            values  = col.distinct(query["field"], query.get("filter", {}))
            results = [{"_value": v} for v in values]   # wrap for uniform scoring

        elif op == "aggregate":
            results = list(col.aggregate(query["pipeline"]))
            _stringify_ids(results)

        else:
            return {"results": [], "error": f"Unknown op: '{op}'"}

        return {"results": results, "error": None}

    except Exception as e:
        return {"results": [], "error": str(e)}


def _stringify_ids(docs: list) -> None:
    for doc in docs:
        if "_id" in doc:
            doc["_id"] = str(doc["_id"])


# ── 5. Scoring ────────────────────────────────────────────────────────────────

def score(gold: list, generated: list, op: str, projection_fields: set | None = None) -> dict:
    """
    Compute precision, recall, and F1 between two result sets.

    Comparison strategy by op:
        find      — compare by content using only the gold projection fields.
                    If the generated query returns extra fields, they are ignored.
        distinct  — compare scalar values directly.
        aggregate — compare by values only, ignoring output field name aliases.

    projection_fields: set of field names from the gold projection (find only).
    """
    gold_keys = _to_keys(gold, op, projection_fields)
    gen_keys  = _to_keys(generated, op, projection_fields)

    if not gold_keys and not gen_keys:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0, "tp": 0, "gold_n": 0, "gen_n": 0}

    tp        = len(gold_keys & gen_keys)
    precision = tp / len(gen_keys)  if gen_keys  else 0.0
    recall    = tp / len(gold_keys) if gold_keys else 0.0
    f1        = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    return {
        "precision": round(precision, 4),
        "recall":    round(recall,    4),
        "f1":        round(f1,        4),
        "tp":        tp,
        "gold_n":    len(gold_keys),
        "gen_n":     len(gen_keys),
    }


def is_match(scores: dict, threshold: float) -> bool:
    """
    A result is a match if:
      - All gold documents were found (recall == 1.0)
      - Document noise is within threshold (precision >= threshold)
      - All gold fields were included (projection recall == 1.0)
        Only applied when a projection score exists.
    """
    if scores["recall"] < 1.0:
        return False
    if scores["precision"] < threshold:
        return False
    proj = scores.get("projection_score")
    if proj and proj["recall"] < 1.0:
        return False
    return True


def projection_score(gold_query: dict, generated_query: dict) -> dict | None:
    """
    Measure how well the generated projection matches the gold projection.
    Only applies to find queries with an explicit gold projection.

    Returns a dict with two scores, or None if not applicable:

        recall    — fraction of gold fields included in generated (0.0–1.0)
                    penalises missing fields
        precision — fraction of generated fields that are in gold (0.0–1.0)
                    penalises extra fields

    Examples:
        gold=[navn, orgNr]  generated=[navn, orgNr]
            → recall=1.0, precision=1.0

        gold=[navn, orgNr]  generated=[navn, orgNr, uuid, konkursFlagg]
            → recall=1.0, precision=0.5  (2 of 4 generated fields are in gold)

        gold=[navn, orgNr, etablertDato]  generated=[navn, orgNr]
            → recall=0.67, precision=1.0  (missing etablertDato)

        generated has no projection (returns all fields):
            → recall=1.0, precision=None  (all gold fields present, but total unknown)
    """
    if gold_query.get("op") != "find":
        return None

    gold_proj = {k for k, v in gold_query.get("projection", {}).items() if k != "_id" and v}
    if not gold_proj:
        return None

    gen_proj = {k for k, v in generated_query.get("projection", {}).items() if k != "_id" and v}

    if not gen_proj:
        # No projection — all fields returned, so all gold fields are present.
        # Precision is None because we cannot count the total generated fields.
        return {"recall": 1.0, "precision": None}

    overlap   = len(gold_proj & gen_proj)
    recall    = round(overlap / len(gold_proj), 4)
    precision = round(overlap / len(gen_proj),  4)
    return {"recall": recall, "precision": precision}


def _to_keys(results: list, op: str, projection_fields: set | None = None) -> set:
    if op == "distinct":
        # Scalar values — compare directly.
        return {str(r.get("_value", r)) for r in results}

    if op == "aggregate":
        # Compare by values only, ignoring output field names.
        # Aggregate output field names are aliases invented by the query writer
        # (e.g. "antall" vs "antallKonkurser") and carry no semantic meaning.
        # The data is correct as long as the values match.
        return {json.dumps(sorted(r.values(), key=str), default=str) for r in results}

    # find: compare only the fields that the gold projection requested.
    # If the generated query returns extra fields (no projection or wider projection),
    # those fields are ignored — only the requested fields need to be correct.
    # _id is always excluded since gold projections often suppress it.
    def _trim(doc: dict) -> dict:
        clean = {k: v for k, v in doc.items() if k != "_id"}
        if projection_fields:
            clean = {k: v for k, v in clean.items() if k in projection_fields}
        return clean

    return {json.dumps(_trim(r), sort_keys=True, default=str) for r in results}


# ── 6. Evaluation ─────────────────────────────────────────────────────────────

def evaluate_question(entry: dict, schema_text: str, threshold: float, database: str | None = None) -> dict:
    """
    Run the full pipeline for one benchmark question.

    Benchmark entry fields:
        question   — natural language question (required)
        gold       — gold MongoDB query object (required)
        id         — identifier for cross-run tracking (optional)
        category   — label for breakdown analysis, e.g. "filter", "aggregation" (optional)
    """
    gold  = entry["gold"]
    op    = gold.get("op", "find")

    result = {
        "id":               entry.get("id"),
        "question":         entry["question"],
        "category":         entry.get("category"),
        "op":               op,
        "gold_query":       gold,
        "generated_query":  None,
        "sample":           None,
        "scores":           None,
        "match":            False,
        "status":           "ok",    # ok | llm_error | db_error
        "error":            None,
    }

    # Step 1 — generate query
    llm = generate_query(schema_text, entry["question"])
    if llm["error"]:
        result.update(status="llm_error", error=llm["error"])
        return result
    result["generated_query"] = llm["query"]

    # Step 2 — run both queries
    gold_run = run_query(gold, database)
    if gold_run["error"]:
        result.update(status="db_error", error=gold_run["error"])
        return result

    gen_run = run_query(llm["query"], database)
    if gen_run["error"]:
        result.update(status="db_error", error=gen_run["error"])
        return result

    # Step 3 — score
    # Extract the projected field names from the gold query (find only).
    # Used to trim generated results before comparison so extra fields are ignored.
    gold_projection = gold.get("projection", {})
    projection_fields = {k for k, v in gold_projection.items() if k != "_id" and v} or None

    scores = score(gold_run["results"], gen_run["results"], op, projection_fields)
    scores["projection_score"] = projection_score(gold, llm["query"])
    result.update(
        scores=scores,
        match=is_match(scores, threshold),
        sample={
            "gold":      gold_run["results"][:3],
            "generated": gen_run["results"][:3],
        },
    )
    return result


# ── 7. Results ────────────────────────────────────────────────────────────────

def run_evaluation(schema_path: str, benchmark_path: str, label: str, threshold: float, database: str | None = None):
    """Run the full evaluation and save results to the results/ directory."""
    print(f"\n{'='*60}")
    print(f"  {label}")
    db_name = database or config.DATABASE_NAME
    print(f"  model={config.MODEL} db={db_name} schema={Path(schema_path).name}  threshold={threshold}")
    print(f"{'='*60}\n")

    schema_text = load_schema(schema_path)
    benchmark   = load_benchmark(benchmark_path)
    question_results = []

    for i, entry in enumerate(benchmark, 1):
        op = entry.get("gold", {}).get("op", "find")
        print(f"  [{i}/{len(benchmark)}] [{op}] {entry['question'][:55]}...")

        r = evaluate_question(entry, schema_text, threshold, database)
        question_results.append(r)

        if r["status"] == "ok":
            s = r["scores"]
            tag = "✓ MATCH" if r["match"] else "✗ no match"
            print(f"           {tag}  P={s['precision']:.2f}  R={s['recall']:.2f}  F1={s['f1']:.2f}")
        else:
            print(f"           ✗ ERROR ({r['status']}): {r['error']}")

    summary = _summarise(question_results)
    _print_summary(summary)
    _save(label, schema_path, benchmark_path, threshold, question_results, summary, database)


def _avg_projection(scored: list[dict]) -> dict | None:
    """Average projection recall and precision across find questions that have a projection score."""
    proj = [r["scores"]["projection_score"] for r in scored if r["scores"].get("projection_score") is not None]
    if not proj:
        return None
    recalls    = [p["recall"]    for p in proj]
    precisions = [p["precision"] for p in proj if p["precision"] is not None]
    return {
        "avg_recall":    round(sum(recalls)    / len(recalls),    4),
        "avg_precision": round(sum(precisions) / len(precisions), 4) if precisions else None,
    }


def _summarise(results: list[dict]) -> dict:
    """Compute aggregate metrics with breakdowns by op and category."""
    scored  = [r for r in results if r["scores"]]
    failed  = [r for r in results if r["status"] != "ok"]
    matches = sum(1 for r in scored if r["match"])

    def breakdown(group_key: str) -> dict:
        groups: dict[str, list] = {}
        for r in scored:
            groups.setdefault(r.get(group_key) or "uncategorized", []).append(r)
        return {
            name: {
                "n":          len(items),
                "matches":    sum(1 for r in items if r["match"]),
                "match_rate": round(sum(1 for r in items if r["match"]) / len(items), 4),
                "avg_f1":     round(sum(r["scores"]["f1"] for r in items) / len(items), 4),
                "avg_precision": round(sum(r["scores"]["precision"] for r in items) / len(items), 4),
                "avg_recall":    round(sum(r["scores"]["recall"]    for r in items) / len(items), 4),
            }
            for name, items in groups.items()
        }

    return {
        "total":      len(results),
        "scored":     len(scored),
        "matches":    matches,
        "match_rate": round(matches / len(scored), 4) if scored else 0,
        "avg_precision": round(sum(r["scores"]["precision"] for r in scored) / len(scored), 4) if scored else 0,
        "avg_recall":    round(sum(r["scores"]["recall"]    for r in scored) / len(scored), 4) if scored else 0,
        "avg_f1":        round(sum(r["scores"]["f1"]        for r in scored) / len(scored), 4) if scored else 0,
        "avg_projection_score": _avg_projection(scored),
        "errors": {
            "total":     len(failed),
            "llm_error": sum(1 for r in failed if r["status"] == "llm_error"),
            "db_error":  sum(1 for r in failed if r["status"] == "db_error"),
        },
        "by_op":       breakdown("op"),
        "by_category": breakdown("category"),
    }


def _print_summary(s: dict):
    print(f"\n{'='*60}  Summary")
    print(f"  Match rate:  {s['match_rate']:.1%}  ({s['matches']}/{s['scored']})")
    print(f"  Precision:   {s['avg_precision']:.4f}")
    print(f"  Recall:      {s['avg_recall']:.4f}")
    print(f"  F1:          {s['avg_f1']:.4f}")

    proj = s.get("avg_projection_score")
    if proj is not None:
        p_str = f"{proj['avg_precision']:.4f}" if proj["avg_precision"] is not None else "N/A"
        print(f"  Projection:  recall={proj['avg_recall']:.4f}  precision={p_str}")

    print(f"\n  By operation:")
    for op, v in s["by_op"].items():
        print(f"    {op:<12}  match={v['match_rate']:.1%}  f1={v['avg_f1']:.4f}  (n={v['n']})")

    if any(k != "uncategorized" for k in s["by_category"]):
        print(f"\n  By category:")
        for cat, v in s["by_category"].items():
            print(f"    {cat:<20}  match={v['match_rate']:.1%}  f1={v['avg_f1']:.4f}  (n={v['n']})")

    if s["errors"]["total"]:
        print(f"\n  Errors: {s['errors']['total']}  "
              f"(llm={s['errors']['llm_error']}, db={s['errors']['db_error']})")
    print()


def _save(label, schema_path, benchmark_path, threshold, question_results, summary, database):
    Path(config.RESULTS_DIR).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path      = f"{config.RESULTS_DIR}/{timestamp}_{label}.json"

    # Split questions into scored and failed for cleaner result files
    scored = [r for r in question_results if r["status"] == "ok"]
    failed = [
        {"id": r["id"], "question": r["question"], "status": r["status"], "error": r["error"]}
        for r in question_results if r["status"] != "ok"
    ]

    report = {
        "run": {
            "label":     label,
            "timestamp": timestamp,
            "model":     config.MODEL,
            "schema":    Path(schema_path).name,
            "benchmark": Path(benchmark_path).name,
            "database": database or config.DATABASE_NAME,
            "threshold": threshold,
        },
        "summary": summary,
        "questions": scored,
        "failures":  failed,
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str, ensure_ascii=False)

    print(f"  Saved → {path}\n")