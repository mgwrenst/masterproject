import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import config

CACHE_VERSION = 2


def load_gold_cache(
    benchmark_path: str | Path,
    database_name: str,
    entry: dict[str, Any],
    cache_dir: str | Path | None = None,
) -> dict[str, Any] | None:
    path = gold_cache_path(benchmark_path, database_name, entry, cache_dir)
    if not path.exists():
        return None

    with open(path, encoding="utf-8") as file:
        cached = json.load(file)

    result = cached["result"]
    return {
        "results": result["results"],
        "error": None,
        "duration_ms": 0,
        "result_count": result["result_count"],
        "cache": {
            "hit": True,
            "path": str(path),
            "created_at": cached["metadata"].get("created_at"),
        },
    }


def save_gold_cache(
    benchmark_path: str | Path,
    database_name: str,
    entry: dict[str, Any],
    query_result: dict[str, Any],
    cache_dir: str | Path | None = None,
) -> Path | None:
    if query_result.get("error"):
        return None

    path = gold_cache_path(benchmark_path, database_name, entry, cache_dir)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "metadata": {
            "cache_version": CACHE_VERSION,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "benchmark": str(benchmark_path),
            "benchmark_name": Path(benchmark_path).stem,
            "database": database_name,
            "id": entry.get("id"),
            "question": entry.get("question"),
            "query_hash": gold_cache_key(benchmark_path, database_name, entry),
        },
        "gold_query": entry["gold"],
        "result": {
            "result_count": query_result.get("result_count", len(query_result.get("results", []))),
            "results": query_result.get("results", []),
        },
    }

    with open(path, "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, ensure_ascii=False, default=str)

    return path


def gold_cache_path(
    benchmark_path: str | Path,
    database_name: str,
    entry: dict[str, Any],
    cache_dir: str | Path | None = None,
) -> Path:
    root = Path(cache_dir or config.GOLD_CACHE_DIR)
    benchmark_name = safe_path_part(Path(benchmark_path).stem)
    database = safe_path_part(database_name)
    question_id = safe_path_part(str(entry.get("id", "unknown")))
    cache_key = gold_cache_key(benchmark_path, database_name, entry)
    return root / benchmark_name / database / f"q{question_id}_{cache_key[:16]}.json"


def gold_cache_key(benchmark_path: str | Path, database_name: str, entry: dict[str, Any]) -> str:
    payload = {
        "cache_version": CACHE_VERSION,
        "benchmark_name": Path(benchmark_path).stem,
        "database": database_name,
        "id": entry.get("id"),
        "question": entry.get("question"),
        "gold": entry["gold"],
    }
    return hashlib.sha256(stable_json(payload).encode("utf-8")).hexdigest()


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def safe_path_part(value: str) -> str:
    safe = []
    for character in value:
        if character.isalnum() or character in ("-", "_", "."):
            safe.append(character)
        else:
            safe.append("_")
    return "".join(safe)
