import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, stdev
from typing import Any


METRICS = ("success_rate", "avg_precision", "avg_recall", "avg_f1")
QUESTION_METRICS = ("precision", "recall", "f1")


@dataclass(frozen=True)
class ResultFile:
    path: Path
    data: dict[str, Any]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze text-to-query evaluation result JSON files and create thesis-ready tables."
    )
    parser.add_argument("--results-dir", default="results", help="Root folder containing evaluation JSON files.")
    parser.add_argument("--output-dir", default="results/analysis", help="Folder where analysis files are written.")
    parser.add_argument(
        "--include-analysis-json",
        action="store_true",
        help="Also read JSON files under the analysis folder. Normally these are skipped.",
    )
    parser.add_argument(
        "--latest-only",
        action="store_true",
        help="Keep only the latest run for each benchmark/structure/schema/model/run-number key.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    results_dir = Path(args.results_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    result_files = load_result_files(results_dir, output_dir, args.include_analysis_json)
    if args.latest_only:
        result_files = latest_result_files(result_files)

    run_rows = [run_record(item) for item in result_files]
    question_rows = [
        question_record(item, question)
        for item in result_files
        for question in item.data.get("questions", [])
    ]

    grouped_runs = aggregate_runs(run_rows)
    category_rows = aggregate_questions(
        question_rows,
        ["benchmark_set", "structure", "schema_version", "model", "category"],
    )
    operation_rows = aggregate_questions(
        question_rows,
        ["benchmark_set", "structure", "schema_version", "model", "operation"],
    )
    question_by_config_rows = aggregate_questions(
        question_rows,
        ["benchmark_set", "structure", "schema_version", "model", "question_id"],
        include_question_text=True,
    )
    question_difficulty_rows = aggregate_questions(
        question_rows,
        ["benchmark_set", "question_id"],
        include_question_text=True,
    )
    failure_rows = [row for row in question_rows if not row["success"] or row["status"] != "ok"]

    model_comparison_rows = compare_dimension(
        question_rows,
        grouped_runs,
        dimension="model",
        left_value="gpt-4.1-mini",
        right_value="gpt-5-mini",
        fixed_fields=["benchmark_set", "structure", "schema_version"],
        label="gpt-5-mini minus gpt-4.1-mini",
    )
    schema_comparison_rows = compare_dimension(
        question_rows,
        grouped_runs,
        dimension="schema_version",
        left_value="naive",
        right_value="advanced",
        fixed_fields=["benchmark_set", "structure", "model"],
        label="advanced minus naive",
    )
    structure_comparison_rows = compare_dimension(
        question_rows,
        grouped_runs,
        dimension="structure",
        left_value="flat",
        right_value="structured",
        fixed_fields=["benchmark_set", "schema_version", "model"],
        label="structured minus flat",
    )

    findings = build_findings(
        run_rows=run_rows,
        grouped_runs=grouped_runs,
        category_rows=category_rows,
        question_difficulty_rows=question_difficulty_rows,
        failure_rows=failure_rows,
        model_comparison_rows=model_comparison_rows,
        schema_comparison_rows=schema_comparison_rows,
        structure_comparison_rows=structure_comparison_rows,
    )

    write_csv(output_dir / "run_level.csv", run_rows)
    write_csv(output_dir / "run_group_summary.csv", grouped_runs)
    write_csv(output_dir / "category_summary.csv", category_rows)
    write_csv(output_dir / "operation_summary.csv", operation_rows)
    write_csv(output_dir / "question_by_config.csv", question_by_config_rows)
    write_csv(output_dir / "question_difficulty.csv", question_difficulty_rows)
    write_csv(output_dir / "failure_cases.csv", failure_rows)
    write_csv(output_dir / "model_comparison.csv", model_comparison_rows)
    write_csv(output_dir / "schema_comparison.csv", schema_comparison_rows)
    write_csv(output_dir / "structure_comparison.csv", structure_comparison_rows)

    write_json(output_dir / "deep_analysis.json", findings)
    write_markdown(output_dir / "key_findings.md", findings)

    print(f"Analyzed {len(run_rows)} run files and {len(question_rows)} question results.")
    print(f"Wrote analysis outputs to {output_dir}")


def load_result_files(results_dir: Path, output_dir: Path, include_analysis_json: bool) -> list[ResultFile]:
    files = []
    output_dir_resolved = output_dir.resolve()
    for path in sorted(results_dir.rglob("*.json")):
        if path.name.startswith("."):
            continue
        if not include_analysis_json and is_relative_to(path.resolve(), output_dir_resolved):
            continue
        try:
            with path.open(encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or "run" not in data or "summary" not in data:
            continue
        files.append(ResultFile(path=path, data=data))
    return files


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def latest_result_files(result_files: list[ResultFile]) -> list[ResultFile]:
    latest: dict[tuple[Any, ...], ResultFile] = {}
    for item in result_files:
        record = run_record(item)
        key = (
            record["benchmark_set"],
            record["structure"],
            record["schema_version"],
            record["model"],
            record["run_number"],
        )
        current = latest.get(key)
        if current is None or timestamp(item) > timestamp(current):
            latest[key] = item
    return sorted(latest.values(), key=lambda item: str(item.path))


def timestamp(item: ResultFile) -> str:
    return str(item.data.get("run", {}).get("timestamp", ""))


def run_record(item: ResultFile) -> dict[str, Any]:
    run = item.data.get("run", {})
    summary = item.data.get("summary", {})
    benchmark_name = Path(str(run.get("benchmark", item.path.parent.parent.name))).stem
    schema_name = Path(str(run.get("schema", item.path.parent.name))).stem
    structure = infer_structure(run, benchmark_name, schema_name)
    schema_version = infer_schema_version(schema_name)
    benchmark_set = "complex" if "complex" in benchmark_name else "normal"
    timing = summary.get("timing_ms", {}) or {}
    errors = summary.get("errors", {}) or {}

    return {
        "path": str(item.path),
        "timestamp": run.get("timestamp"),
        "label": run.get("label"),
        "benchmark": run.get("benchmark"),
        "benchmark_set": benchmark_set,
        "structure": structure,
        "schema": run.get("schema"),
        "schema_description": schema_name,
        "schema_version": schema_version,
        "model": run.get("model"),
        "run_number": infer_run_number(run.get("label")),
        "database": run.get("database"),
        "total_questions": number(summary.get("total_questions")),
        "scored_questions": number(summary.get("scored_questions")),
        "successful_questions": number(summary.get("successful_questions")),
        "failed_questions": number(summary.get("failed_questions")),
        "success_rate": number(summary.get("success_rate")),
        "avg_precision": number(summary.get("avg_precision")),
        "avg_recall": number(summary.get("avg_recall")),
        "avg_f1": number(summary.get("avg_f1")),
        "total_run_ms": number(timing.get("total_run")),
        "avg_per_question_ms": number(timing.get("avg_per_question")),
        "avg_llm_ms": number(timing.get("avg_llm")),
        "avg_generated_query_ms": number(timing.get("avg_generated_query")),
        "avg_scoring_ms": number(timing.get("avg_scoring")),
        "errors_total": number(errors.get("total")),
        "llm_errors": number(errors.get("llm_error")),
        "gold_query_errors": number(errors.get("gold_query_error")),
        "generated_query_errors": number(errors.get("generated_query_error")),
    }


def infer_structure(run: dict[str, Any], benchmark_name: str, schema_name: str) -> str:
    database = str(run.get("database", "")).lower()
    source = " ".join([benchmark_name, schema_name, database])
    if "structured" in source:
        return "structured"
    if "flat" in source or "groundtruth" in database:
        return "flat"
    return "unknown"


def infer_schema_version(schema_name: str) -> str:
    if schema_name.endswith("_advanced") or "advanced" in schema_name:
        return "advanced"
    if schema_name.endswith("_naive") or "naive" in schema_name:
        return "naive"
    return "unknown"


def infer_run_number(label: Any) -> str:
    if not isinstance(label, str):
        return ""
    marker = "_run"
    if marker not in label:
        return ""
    return label.rsplit(marker, 1)[-1]


def question_record(item: ResultFile, question: dict[str, Any]) -> dict[str, Any]:
    base = run_record(item)
    scores = question.get("scores", {}) or {}
    counts = question.get("counts", {}) or {}
    timing = question.get("timing_ms", {}) or {}
    projection_score = question.get("projection_score") or {}
    status = question.get("status", "")
    success = bool(question.get("success", question.get("match", False)))
    return {
        "path": base["path"],
        "timestamp": base["timestamp"],
        "label": base["label"],
        "benchmark_set": base["benchmark_set"],
        "structure": base["structure"],
        "schema_version": base["schema_version"],
        "schema_description": base["schema_description"],
        "model": base["model"],
        "run_number": base["run_number"],
        "question_id": question.get("id"),
        "question": question.get("question"),
        "category": question.get("category", "uncategorized"),
        "operation": question.get("operation"),
        "status": status,
        "success": success,
        "failure_reason": question.get("failure_reason") or question.get("error"),
        "precision": number(scores.get("precision")),
        "recall": number(scores.get("recall")),
        "f1": number(scores.get("f1")),
        "true_positive": number(scores.get("true_positive")),
        "gold_count": number(scores.get("gold_count", counts.get("gold"))),
        "generated_count": number(scores.get("generated_count", counts.get("generated"))),
        "missing_count": number(scores.get("missing_count")),
        "extra_count": number(scores.get("extra_count")),
        "comparison_mode": scores.get("comparison_mode"),
        "empty_result_equivalence": bool(scores.get("empty_result_equivalence", False)),
        "projection_precision": number(projection_score.get("precision")),
        "projection_recall": number(projection_score.get("recall")),
        "llm_ms": number(timing.get("llm")),
        "gold_query_ms": number(timing.get("gold_query")),
        "generated_query_ms": number(timing.get("generated_query")),
        "scoring_ms": number(timing.get("scoring")),
        "total_ms": number(timing.get("total")),
    }


def aggregate_runs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups = group_by(rows, ["benchmark_set", "structure", "schema_version", "model"])
    output = []
    for key, items in groups.items():
        row = dict(zip(["benchmark_set", "structure", "schema_version", "model"], key))
        row["runs"] = len(items)
        row["total_questions_per_run"] = first_non_null(items, "total_questions")
        row["mean_success_rate"] = avg(items, "success_rate")
        row["sd_success_rate"] = sample_sd(items, "success_rate")
        row["min_success_rate"] = min_value(items, "success_rate")
        row["max_success_rate"] = max_value(items, "success_rate")
        row["mean_precision"] = avg(items, "avg_precision")
        row["mean_recall"] = avg(items, "avg_recall")
        row["mean_f1"] = avg(items, "avg_f1")
        row["sd_f1"] = sample_sd(items, "avg_f1")
        row["mean_total_run_ms"] = avg(items, "total_run_ms")
        row["mean_avg_per_question_ms"] = avg(items, "avg_per_question_ms")
        row["total_errors"] = sum_value(items, "errors_total")
        row["total_llm_errors"] = sum_value(items, "llm_errors")
        row["total_generated_query_errors"] = sum_value(items, "generated_query_errors")
        output.append(round_row(row))
    return sorted(output, key=lambda row: (row["benchmark_set"], row["structure"], row["schema_version"], row["model"]))


def aggregate_questions(
    rows: list[dict[str, Any]],
    fields: list[str],
    include_question_text: bool = False,
) -> list[dict[str, Any]]:
    groups = group_by(rows, fields)
    output = []
    for key, items in groups.items():
        row = dict(zip(fields, key))
        if include_question_text:
            row["question"] = first_non_null(items, "question")
            row["category"] = first_non_null(items, "category")
            row["operation"] = first_non_null(items, "operation")
        row["question_runs"] = len(items)
        row["unique_questions"] = len({item.get("question_id") for item in items})
        row["successes"] = sum(1 for item in items if item.get("success"))
        row["success_rate"] = row["successes"] / row["question_runs"] if row["question_runs"] else None
        row["avg_precision"] = avg(items, "precision")
        row["avg_recall"] = avg(items, "recall")
        row["avg_f1"] = avg(items, "f1")
        row["sd_f1"] = sample_sd(items, "f1")
        row["avg_gold_count"] = avg(items, "gold_count")
        row["avg_generated_count"] = avg(items, "generated_count")
        row["avg_missing_count"] = avg(items, "missing_count")
        row["avg_extra_count"] = avg(items, "extra_count")
        row["errors"] = sum(1 for item in items if item.get("status") != "ok")
        row["avg_total_ms"] = avg(items, "total_ms")
        output.append(round_row(row))
    return sorted(output, key=sort_aggregate_row)


def compare_dimension(
    question_rows: list[dict[str, Any]],
    grouped_runs: list[dict[str, Any]],
    dimension: str,
    left_value: str,
    right_value: str,
    fixed_fields: list[str],
    label: str,
) -> list[dict[str, Any]]:
    run_lookup = {
        tuple(row[field] for field in ["benchmark_set", "structure", "schema_version", "model"]): row
        for row in grouped_runs
    }
    dimension_values = {left_value, right_value}
    candidate_keys = {
        tuple(row[field] for field in fixed_fields)
        for row in question_rows
        if row.get(dimension) in dimension_values
    }

    output = []
    for key in sorted(candidate_keys):
        left_key = dict(zip(fixed_fields, key))
        right_key = dict(zip(fixed_fields, key))
        left_key[dimension] = left_value
        right_key[dimension] = right_value

        left_run_key = run_key_from_parts(left_key)
        right_run_key = run_key_from_parts(right_key)
        if left_run_key not in run_lookup or right_run_key not in run_lookup:
            continue

        left_questions = matching_question_averages(question_rows, left_key)
        right_questions = matching_question_averages(question_rows, right_key)
        shared_ids = sorted(set(left_questions) & set(right_questions), key=lambda value: str(value))
        deltas = [right_questions[question_id]["avg_f1"] - left_questions[question_id]["avg_f1"] for question_id in shared_ids]
        right_wins = sum(1 for value in deltas if value > 0.000001)
        left_wins = sum(1 for value in deltas if value < -0.000001)
        ties = len(deltas) - right_wins - left_wins

        row = dict(zip(fixed_fields, key))
        row["comparison"] = label
        row["left"] = left_value
        row["right"] = right_value
        row["left_success_rate"] = run_lookup[left_run_key]["mean_success_rate"]
        row["right_success_rate"] = run_lookup[right_run_key]["mean_success_rate"]
        row["delta_success_rate"] = row["right_success_rate"] - row["left_success_rate"]
        row["left_f1"] = run_lookup[left_run_key]["mean_f1"]
        row["right_f1"] = run_lookup[right_run_key]["mean_f1"]
        row["delta_f1"] = row["right_f1"] - row["left_f1"]
        row["shared_questions"] = len(shared_ids)
        row["right_wins"] = right_wins
        row["left_wins"] = left_wins
        row["ties"] = ties
        row["largest_right_gains"] = format_question_deltas(shared_ids, left_questions, right_questions, reverse=True)
        row["largest_left_gains"] = format_question_deltas(shared_ids, left_questions, right_questions, reverse=False)
        output.append(round_row(row))
    return output


def run_key_from_parts(parts: dict[str, Any]) -> tuple[Any, ...]:
    return (
        parts.get("benchmark_set"),
        parts.get("structure"),
        parts.get("schema_version"),
        parts.get("model"),
    )


def matching_question_averages(rows: list[dict[str, Any]], filters: dict[str, Any]) -> dict[Any, dict[str, Any]]:
    matches = [
        row for row in rows
        if all(row.get(field) == value for field, value in filters.items())
    ]
    groups = group_by(matches, ["question_id"])
    return {
        question_id: {
            "avg_f1": avg(items, "f1") or 0,
            "success_rate": sum(1 for item in items if item.get("success")) / len(items),
            "question": first_non_null(items, "question"),
        }
        for (question_id,), items in groups.items()
    }


def format_question_deltas(
    question_ids: list[Any],
    left_questions: dict[Any, dict[str, Any]],
    right_questions: dict[Any, dict[str, Any]],
    reverse: bool,
    limit: int = 5,
) -> str:
    rows = []
    for question_id in question_ids:
        delta = right_questions[question_id]["avg_f1"] - left_questions[question_id]["avg_f1"]
        rows.append((delta, question_id))
    rows.sort(reverse=reverse)
    selected = [(delta, question_id) for delta, question_id in rows if abs(delta) > 0.000001][:limit]
    return "; ".join(f"Q{question_id} ({delta:+.4f})" for delta, question_id in selected)


def build_findings(
    run_rows: list[dict[str, Any]],
    grouped_runs: list[dict[str, Any]],
    category_rows: list[dict[str, Any]],
    question_difficulty_rows: list[dict[str, Any]],
    failure_rows: list[dict[str, Any]],
    model_comparison_rows: list[dict[str, Any]],
    schema_comparison_rows: list[dict[str, Any]],
    structure_comparison_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    best_runs = sorted(grouped_runs, key=lambda row: row.get("mean_success_rate") or 0, reverse=True)[:10]
    worst_runs = sorted(grouped_runs, key=lambda row: row.get("mean_success_rate") or 0)[:10]
    hardest_categories = sorted(category_rows, key=lambda row: (row.get("success_rate") or 0, row.get("avg_f1") or 0))[:15]
    easiest_categories = sorted(category_rows, key=lambda row: (row.get("success_rate") or 0, row.get("avg_f1") or 0), reverse=True)[:15]
    hardest_questions = sorted(question_difficulty_rows, key=lambda row: (row.get("success_rate") or 0, row.get("avg_f1") or 0))[:20]
    slowest_questions = sorted(question_difficulty_rows, key=lambda row: row.get("avg_total_ms") or 0, reverse=True)[:20]

    failure_reasons = Counter(row.get("failure_reason") or row.get("status") or "unknown" for row in failure_rows)
    zero_zero = [
        row for row in failure_rows
        if row.get("precision") == 0 and row.get("recall") == 0
    ]
    same_count_zero_zero = [
        row for row in zero_zero
        if row.get("gold_count") == row.get("generated_count")
    ]

    return {
        "overview": {
            "run_files": len(run_rows),
            "run_groups": len(grouped_runs),
            "benchmarks": sorted({row["benchmark_set"] for row in run_rows}),
            "models": sorted({row["model"] for row in run_rows}),
            "structures": sorted({row["structure"] for row in run_rows}),
            "schema_versions": sorted({row["schema_version"] for row in run_rows}),
            "question_runs": sum(int(row.get("total_questions") or 0) for row in run_rows),
            "failure_question_runs": len(failure_rows),
        },
        "best_run_groups": best_runs,
        "worst_run_groups": worst_runs,
        "hardest_categories": hardest_categories,
        "easiest_categories": easiest_categories,
        "hardest_questions": hardest_questions,
        "slowest_questions": slowest_questions,
        "failure_patterns": {
            "failure_reason_counts": dict(failure_reasons.most_common()),
            "zero_precision_zero_recall": len(zero_zero),
            "zero_zero_same_gold_generated_count": len(same_count_zero_zero),
            "same_count_zero_zero_examples": same_count_zero_zero[:20],
        },
        "model_comparison": model_comparison_rows,
        "schema_comparison": schema_comparison_rows,
        "structure_comparison": structure_comparison_rows,
    }


def write_markdown(path: Path, findings: dict[str, Any]) -> None:
    lines = [
        "# Result Analysis",
        "",
        "Generated by `python src/text_to_query/analyze_results.py`.",
        "",
        "## Scope",
        "",
    ]
    overview = findings["overview"]
    lines.extend(
        [
            f"- Run files analyzed: {overview['run_files']}",
            f"- Run groups: {overview['run_groups']}",
            f"- Benchmarks: {', '.join(overview['benchmarks'])}",
            f"- Models: {', '.join(overview['models'])}",
            f"- Question-runs: {overview['question_runs']}",
            f"- Failed/error question-runs: {overview['failure_question_runs']}",
            "",
        ]
    )

    add_table(
        lines,
        "Best Overall Configurations",
        findings["best_run_groups"],
        ["benchmark_set", "structure", "schema_version", "model", "runs", "mean_success_rate", "mean_f1", "sd_f1"],
    )
    add_table(
        lines,
        "Weakest Overall Configurations",
        findings["worst_run_groups"],
        ["benchmark_set", "structure", "schema_version", "model", "runs", "mean_success_rate", "mean_f1", "sd_f1"],
    )
    add_table(
        lines,
        "Hardest Categories",
        findings["hardest_categories"],
        ["benchmark_set", "structure", "schema_version", "model", "category", "success_rate", "avg_f1", "question_runs"],
    )
    add_table(
        lines,
        "Hardest Questions",
        findings["hardest_questions"],
        ["benchmark_set", "question_id", "category", "operation", "success_rate", "avg_f1", "question"],
    )
    add_table(
        lines,
        "Model Comparison",
        findings["model_comparison"],
        ["benchmark_set", "structure", "schema_version", "delta_success_rate", "delta_f1", "right_wins", "left_wins", "ties"],
    )
    add_table(
        lines,
        "Schema Description Comparison",
        findings["schema_comparison"],
        ["benchmark_set", "structure", "model", "delta_success_rate", "delta_f1", "right_wins", "left_wins", "ties"],
    )
    add_table(
        lines,
        "Database Structure Comparison",
        findings["structure_comparison"],
        ["benchmark_set", "schema_version", "model", "delta_success_rate", "delta_f1", "right_wins", "left_wins", "ties"],
    )

    patterns = findings["failure_patterns"]
    lines.extend(
        [
            "## Failure Patterns",
            "",
            f"- Zero precision and zero recall cases: {patterns['zero_precision_zero_recall']}",
            f"- Zero-zero cases with equal gold/generated counts: {patterns['zero_zero_same_gold_generated_count']}",
            "",
            "| Reason | Count |",
            "|---|---:|",
        ]
    )
    for reason, count in list(patterns["failure_reason_counts"].items())[:12]:
        lines.append(f"| {markdown_cell(reason)} | {count} |")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def add_table(lines: list[str], title: str, rows: list[dict[str, Any]], columns: list[str], limit: int = 12) -> None:
    lines.extend([f"## {title}", ""])
    if not rows:
        lines.extend(["No matching data.", ""])
        return
    lines.append("| " + " | ".join(columns) + " |")
    lines.append("| " + " | ".join("---" for _ in columns) + " |")
    for row in rows[:limit]:
        lines.append("| " + " | ".join(markdown_cell(row.get(column)) for column in columns) + " |")
    lines.append("")


def markdown_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.4f}"
    text = str(value).replace("\n", " ").replace("|", "\\|")
    if len(text) > 120:
        return text[:117] + "..."
    return text


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    columns = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, data: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)


def group_by(rows: list[dict[str, Any]], fields: list[str]) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[tuple(row.get(field) for field in fields)].append(row)
    return groups


def first_non_null(rows: list[dict[str, Any]], field: str) -> Any:
    for row in rows:
        value = row.get(field)
        if value is not None and value != "":
            return value
    return None


def number(value: Any) -> float | int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return value
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric.is_integer():
        return int(numeric)
    return numeric


def values(rows: list[dict[str, Any]], field: str) -> list[float]:
    return [
        float(row[field])
        for row in rows
        if isinstance(row.get(field), (int, float)) and not isinstance(row.get(field), bool)
    ]


def avg(rows: list[dict[str, Any]], field: str) -> float | None:
    nums = values(rows, field)
    return mean(nums) if nums else None


def sample_sd(rows: list[dict[str, Any]], field: str) -> float | None:
    nums = values(rows, field)
    return stdev(nums) if len(nums) > 1 else 0 if len(nums) == 1 else None


def min_value(rows: list[dict[str, Any]], field: str) -> float | None:
    nums = values(rows, field)
    return min(nums) if nums else None


def max_value(rows: list[dict[str, Any]], field: str) -> float | None:
    nums = values(rows, field)
    return max(nums) if nums else None


def sum_value(rows: list[dict[str, Any]], field: str) -> float:
    return sum(values(rows, field))


def round_row(row: dict[str, Any]) -> dict[str, Any]:
    rounded = {}
    for key, value in row.items():
        if isinstance(value, float):
            rounded[key] = round(value, 4)
        else:
            rounded[key] = value
    return rounded


def sort_aggregate_row(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("benchmark_set"),
        row.get("structure", ""),
        row.get("schema_version", ""),
        row.get("model", ""),
        row.get("success_rate") if row.get("success_rate") is not None else 999,
        str(row.get("category") or row.get("operation") or row.get("question_id") or ""),
    )


if __name__ == "__main__":
    main()
