import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev
from typing import Any


METRICS = ("success_rate", "avg_precision", "avg_recall", "avg_f1")
METRIC_LABELS = {
    "success_rate": "Success",
    "avg_precision": "Precision",
    "avg_recall": "Recall",
    "avg_f1": "F1",
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def pct(value: float | None) -> str:
    if value is None or math.isnan(value):
        return "--"
    return f"{value * 100:.1f}"


def num(value: float | None, digits: int = 3) -> str:
    if value is None or math.isnan(value):
        return "--"
    return f"{value:.{digits}f}"


def benchmark_set(structure: str, benchmark: str) -> str:
    raw = f"{structure} {benchmark}".lower()
    return "complex" if "complex" in raw else "main"


def structure_base(structure: str) -> str:
    return "structured" if "structured" in structure else "flat"


def schema_version(schema_description: str) -> str:
    return "advanced" if "advanced" in schema_description else "naive"


def normalize_run(path: Path, data: dict[str, Any]) -> dict[str, Any]:
    run = data["run"]
    summary = data["summary"]
    structure = run.get("structure") or Path(run.get("benchmark", "")).stem
    schema_description = Path(run.get("schema", "")).stem
    return {
        "path": str(path),
        "timestamp": run.get("timestamp", ""),
        "label": run.get("label", path.stem),
        "model": run.get("model", ""),
        "structure": structure,
        "structure_base": structure_base(structure),
        "schema_description": schema_description,
        "schema_version": schema_version(schema_description),
        "benchmark": run.get("benchmark", ""),
        "benchmark_set": benchmark_set(structure, run.get("benchmark", "")),
        "total_questions": summary.get("total_questions", 0),
        "scored_questions": summary.get("scored_questions", summary.get("total_questions", 0)),
        "successful_questions": summary.get("successful_questions", 0),
        "failed_questions": summary.get("failed_questions", 0),
        "success_rate": summary.get("success_rate", 0.0),
        "avg_precision": summary.get("avg_precision", 0.0),
        "avg_recall": summary.get("avg_recall", 0.0),
        "avg_f1": summary.get("avg_f1", 0.0),
        "error_total": summary.get("errors", {}).get("total", 0),
        "avg_time_ms": summary.get("timing_ms", {}).get("avg_per_question", 0),
        "by_operation": summary.get("by_operation", {}),
        "by_category": summary.get("by_category", {}),
        "questions": data.get("questions", []),
    }


def load_runs(results_dir: Path) -> list[dict[str, Any]]:
    runs = []
    for path in sorted(results_dir.rglob("*.json")):
        if "analysis" in path.parts:
            continue
        data = load_json(path)
        if "run" in data and "summary" in data:
            runs.append(normalize_run(path, data))
    return runs


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def latex_escape(value: Any) -> str:
    text = str(value)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
    }
    return "".join(replacements.get(char, char) for char in text)


def write_latex_table(
    path: Path,
    caption: str,
    label: str,
    headers: list[str],
    rows: list[list[Any]],
    align: str | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    align = align or ("l" + "r" * (len(headers) - 1))
    lines = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\small",
        rf"\caption{{{latex_escape(caption)}}}",
        rf"\label{{{latex_escape(label)}}}",
        rf"\begin{{tabular}}{{{align}}}",
        r"\toprule",
        " & ".join(latex_escape(header) for header in headers) + r" \\",
        r"\midrule",
    ]
    for row in rows:
        lines.append(" & ".join(latex_escape(value) for value in row) + r" \\")
    lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def summarize_groups(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped = defaultdict(list)
    for run in runs:
        key = (
            run["benchmark_set"],
            run["structure_base"],
            run["schema_version"],
            run["model"],
        )
        grouped[key].append(run)

    rows = []
    for (bench, structure, schema, model), items in sorted(grouped.items()):
        row = {
            "benchmark_set": bench,
            "structure": structure,
            "schema": schema,
            "model": model,
            "runs": len(items),
            "questions_per_run": items[0]["total_questions"] if items else 0,
            "scored_per_run": items[0]["scored_questions"] if items else 0,
            "errors_mean": mean(item["error_total"] for item in items),
            "avg_time_ms_mean": mean(item["avg_time_ms"] for item in items),
        }
        for metric in METRICS:
            values = [item[metric] for item in items]
            row[f"{metric}_mean"] = mean(values)
            row[f"{metric}_std"] = stdev(values) if len(values) > 1 else 0.0
            row[f"{metric}_min"] = min(values)
            row[f"{metric}_max"] = max(values)
        rows.append(row)
    return rows


def comparison_rows(summary_rows: list[dict[str, Any]], dimension: str) -> list[dict[str, Any]]:
    others = {
        "model": ["benchmark_set", "structure", "schema"],
        "schema": ["benchmark_set", "structure", "model"],
        "structure": ["benchmark_set", "schema", "model"],
    }[dimension]
    grouped = defaultdict(dict)
    for row in summary_rows:
        key = tuple(row[field] for field in others)
        grouped[key][row[dimension]] = row

    preferred_pairs = {
        "model": ("gpt-4.1-mini", "gpt-5-mini"),
        "schema": ("naive", "advanced"),
        "structure": ("flat", "structured"),
    }
    left, right = preferred_pairs[dimension]
    rows = []
    for key, values in sorted(grouped.items()):
        if left not in values or right not in values:
            continue
        base = dict(zip(others, key, strict=True))
        left_row = values[left]
        right_row = values[right]
        output = {**base, f"{dimension}_a": left, f"{dimension}_b": right}
        for metric in METRICS:
            output[f"{metric}_a"] = left_row[f"{metric}_mean"]
            output[f"{metric}_b"] = right_row[f"{metric}_mean"]
            output[f"{metric}_delta"] = right_row[f"{metric}_mean"] - left_row[f"{metric}_mean"]
        rows.append(output)
    return rows


def nested_summary_rows(runs: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    grouped = defaultdict(list)
    for run in runs:
        values = run.get(field, {})
        for name, item in values.items():
            key = (
                run["benchmark_set"],
                run["structure_base"],
                run["schema_version"],
                run["model"],
                name,
            )
            grouped[key].append(item)

    rows = []
    for (bench, structure, schema, model, name), items in sorted(grouped.items()):
        row = {
            "benchmark_set": bench,
            "structure": structure,
            "schema": schema,
            "model": model,
            "name": name,
            "runs": len(items),
            "questions_mean": mean(item.get("questions", 0) for item in items),
            "successful_mean": mean(item.get("successful", 0) for item in items),
        }
        for metric in METRICS:
            values = [item.get(metric, 0.0) for item in items]
            row[f"{metric}_mean"] = mean(values)
            row[f"{metric}_std"] = stdev(values) if len(values) > 1 else 0.0
        rows.append(row)
    return rows


def overall_type_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["benchmark_set"], row["name"])].append(row)

    output = []
    for (bench, name), items in sorted(grouped.items()):
        output.append(
            {
                "benchmark_set": bench,
                "name": name,
                "configurations": len(items),
                "questions_mean": mean(item["questions_mean"] for item in items),
                "success_rate_mean": mean(item["success_rate_mean"] for item in items),
                "avg_precision_mean": mean(item["avg_precision_mean"] for item in items),
                "avg_recall_mean": mean(item["avg_recall_mean"] for item in items),
                "avg_f1_mean": mean(item["avg_f1_mean"] for item in items),
            }
        )
    return sorted(output, key=lambda row: (row["benchmark_set"], -row["avg_f1_mean"], row["name"]))


def question_rows(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped = defaultdict(list)
    text = {}
    for run in runs:
        for question in run["questions"]:
            scores = question.get("scores") or {}
            key = (
                run["benchmark_set"],
                question.get("id"),
                run["structure_base"],
                run["schema_version"],
                run["model"],
            )
            grouped[key].append(
                {
                    "success": 1.0 if question.get("success") else 0.0,
                    "f1": scores.get("f1", 0.0),
                    "precision": scores.get("precision", 0.0),
                    "recall": scores.get("recall", 0.0),
                    "status": question.get("status", ""),
                }
            )
            text[(run["benchmark_set"], question.get("id"))] = {
                "question": question.get("question", ""),
                "category": question.get("category", ""),
                "operation": question.get("operation", ""),
            }

    rows = []
    for (bench, qid, structure, schema, model), items in sorted(grouped.items(), key=lambda item: (item[0][0], item[0][1], item[0][2], item[0][3], item[0][4])):
        meta = text[(bench, qid)]
        rows.append(
            {
                "benchmark_set": bench,
                "question_id": qid,
                "structure": structure,
                "schema": schema,
                "model": model,
                "runs": len(items),
                "question": meta["question"],
                "category": meta["category"],
                "operation": meta["operation"],
                "success_rate_mean": mean(item["success"] for item in items),
                "precision_mean": mean(item["precision"] for item in items),
                "recall_mean": mean(item["recall"] for item in items),
                "f1_mean": mean(item["f1"] for item in items),
                "error_runs": sum(1 for item in items if item["status"] != "ok"),
            }
        )
    return rows


def difficulty_rows(question_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped = defaultdict(list)
    meta = {}
    for row in question_data:
        key = (row["benchmark_set"], row["question_id"])
        grouped[key].append(row)
        meta[key] = row

    rows = []
    for key, items in sorted(grouped.items(), key=lambda item: (item[0][0], item[0][1])):
        first = meta[key]
        rows.append(
            {
                "benchmark_set": key[0],
                "question_id": key[1],
                "category": first["category"],
                "operation": first["operation"],
                "question": first["question"],
                "configurations": len(items),
                "success_rate_mean": mean(item["success_rate_mean"] for item in items),
                "f1_mean": mean(item["f1_mean"] for item in items),
                "error_runs": sum(item["error_runs"] for item in items),
            }
        )
    return sorted(rows, key=lambda row: (row["benchmark_set"], row["f1_mean"], row["success_rate_mean"], row["question_id"]))


def write_summary_markdown(
    path: Path,
    runs: list[dict[str, Any]],
    summary_rows: list[dict[str, Any]],
    model_comparison: list[dict[str, Any]],
    schema_comparison: list[dict[str, Any]],
    structure_comparison: list[dict[str, Any]],
    difficult_questions: list[dict[str, Any]],
) -> None:
    best = max(summary_rows, key=lambda row: row["avg_f1_mean"])
    lines = [
        "# Result analysis",
        "",
        f"Generated from {len(runs)} result files.",
        "",
        "## Best aggregate configuration",
        "",
        (
            f"- {best['benchmark_set']} / {best['structure']} / {best['schema']} / {best['model']}: "
            f"success {pct(best['success_rate_mean'])}%, F1 {num(best['avg_f1_mean'])} across {best['runs']} run(s)."
        ),
        "",
        "## Recommended thesis tables",
        "",
        "- `latex/main_config_comparison.tex`: compact overview of the ordinary benchmark.",
        "- `latex/complex_config_comparison.tex`: compact overview of the complex pipeline benchmark.",
        "- `latex/model_comparison.tex`: model-to-model deltas while holding structure and schema description fixed.",
        "- `latex/schema_description_effect.tex`: naive versus advanced schema description deltas.",
        "- `latex/structure_effect.tex`: flat versus structured database deltas.",
        "- `latex/operation_performance.tex`: broad query operation types ranked by average F1.",
        "- `latex/query_type_performance.tex`: detailed query categories ranked by average F1.",
        "- `latex/difficult_questions.tex`: questions with the lowest average F1 across configurations.",
        "",
        "The LaTeX fragments use `booktabs`, so add `\\usepackage{booktabs}` in Overleaf if it is not already included.",
        "",
        "## Notes for interpretation",
        "",
        "- Mean values aggregate repeated runs of the same benchmark, structure, schema description, and model.",
        "- Delta tables report the second condition minus the first condition, so positive values mean the second condition performed better.",
        "- The CSV files contain fuller versions of the same data and are better suited for appendix tables or manual checks.",
        "",
        "## Quick findings",
        "",
    ]

    for title, rows, dim in [
        ("Model effect", model_comparison, "model"),
        ("Schema-description effect", schema_comparison, "schema"),
        ("Structure effect", structure_comparison, "structure"),
    ]:
        if not rows:
            continue
        strongest = max(rows, key=lambda row: abs(row["avg_f1_delta"]))
        lines.append(
            f"- {title}: largest F1 delta is {num(strongest['avg_f1_delta'])} "
            f"for {', '.join(strongest[field] for field in strongest if field in {'benchmark_set', 'structure', 'schema', 'model'})}."
        )

    lines.extend(["", "## Most difficult questions", ""])
    for row in difficult_questions[:10]:
        question = row["question"]
        if len(question) > 140:
            question = question[:137] + "..."
        lines.append(
            f"- Q{row['question_id']} ({row['benchmark_set']}, {row['category']}): "
            f"F1 {num(row['f1_mean'])}, success {pct(row['success_rate_mean'])}% - {question}"
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create thesis-ready analysis tables from saved evaluation results.")
    parser.add_argument("--results-dir", default="results", help="Directory containing result JSON files.")
    parser.add_argument("--output-dir", default="results/analysis", help="Directory for analysis outputs.")
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    output_dir = Path(args.output_dir)
    csv_dir = output_dir / "csv"
    latex_dir = output_dir / "latex"
    output_dir.mkdir(parents=True, exist_ok=True)

    runs = load_runs(results_dir)
    if not runs:
        raise SystemExit(f"No result JSON files found under {results_dir}")

    summary_rows = summarize_groups(runs)
    model_comparison = comparison_rows(summary_rows, "model")
    schema_comparison = comparison_rows(summary_rows, "schema")
    structure_comparison = comparison_rows(summary_rows, "structure")
    operation_rows = nested_summary_rows(runs, "by_operation")
    category_rows = nested_summary_rows(runs, "by_category")
    operation_overall = overall_type_rows(operation_rows)
    category_overall = overall_type_rows(category_rows)
    per_question = question_rows(runs)
    difficult_questions = difficulty_rows(per_question)

    summary_columns = [
        "benchmark_set",
        "structure",
        "schema",
        "model",
        "runs",
        "questions_per_run",
        "scored_per_run",
        "success_rate_mean",
        "success_rate_std",
        "avg_precision_mean",
        "avg_recall_mean",
        "avg_f1_mean",
        "avg_f1_std",
        "errors_mean",
        "avg_time_ms_mean",
    ]
    write_csv(csv_dir / "config_summary.csv", summary_rows, summary_columns)
    write_csv(csv_dir / "run_summary_all.csv", runs, [
        "timestamp", "label", "model", "structure", "structure_base", "schema_description",
        "schema_version", "benchmark", "benchmark_set", "total_questions", "scored_questions",
        "successful_questions", "failed_questions", "success_rate", "avg_precision",
        "avg_recall", "avg_f1", "error_total", "avg_time_ms", "path",
    ])
    write_csv(csv_dir / "model_comparison.csv", model_comparison, [
        "benchmark_set", "structure", "schema", "model_a", "model_b",
        "success_rate_a", "success_rate_b", "success_rate_delta",
        "avg_f1_a", "avg_f1_b", "avg_f1_delta",
    ])
    write_csv(csv_dir / "schema_description_effect.csv", schema_comparison, [
        "benchmark_set", "structure", "model", "schema_a", "schema_b",
        "success_rate_a", "success_rate_b", "success_rate_delta",
        "avg_f1_a", "avg_f1_b", "avg_f1_delta",
    ])
    write_csv(csv_dir / "structure_effect.csv", structure_comparison, [
        "benchmark_set", "schema", "model", "structure_a", "structure_b",
        "success_rate_a", "success_rate_b", "success_rate_delta",
        "avg_f1_a", "avg_f1_b", "avg_f1_delta",
    ])
    write_csv(csv_dir / "operation_summary.csv", operation_rows, [
        "benchmark_set", "structure", "schema", "model", "name", "runs",
        "questions_mean", "successful_mean", "success_rate_mean",
        "avg_precision_mean", "avg_recall_mean", "avg_f1_mean",
    ])
    write_csv(csv_dir / "category_summary.csv", category_rows, [
        "benchmark_set", "structure", "schema", "model", "name", "runs",
        "questions_mean", "successful_mean", "success_rate_mean",
        "avg_precision_mean", "avg_recall_mean", "avg_f1_mean",
    ])
    write_csv(csv_dir / "operation_performance_overall.csv", operation_overall, [
        "benchmark_set", "name", "configurations", "questions_mean",
        "success_rate_mean", "avg_precision_mean", "avg_recall_mean", "avg_f1_mean",
    ])
    write_csv(csv_dir / "query_type_performance_overall.csv", category_overall, [
        "benchmark_set", "name", "configurations", "questions_mean",
        "success_rate_mean", "avg_precision_mean", "avg_recall_mean", "avg_f1_mean",
    ])
    write_csv(csv_dir / "per_question_by_config.csv", per_question, [
        "benchmark_set", "question_id", "structure", "schema", "model", "runs",
        "category", "operation", "success_rate_mean", "precision_mean",
        "recall_mean", "f1_mean", "error_runs", "question",
    ])
    write_csv(csv_dir / "question_difficulty.csv", difficult_questions, [
        "benchmark_set", "question_id", "category", "operation", "configurations",
        "success_rate_mean", "f1_mean", "error_runs", "question",
    ])

    for bench in ("main", "complex"):
        rows = [row for row in summary_rows if row["benchmark_set"] == bench]
        table_rows = [
            [
                row["structure"].title(),
                row["schema"].title(),
                row["model"],
                row["runs"],
                pct(row["success_rate_mean"]),
                num(row["avg_precision_mean"]),
                num(row["avg_recall_mean"]),
                num(row["avg_f1_mean"]),
            ]
            for row in rows
        ]
        write_latex_table(
            latex_dir / f"{bench}_config_comparison.tex",
            f"{bench.title()} benchmark performance by configuration.",
            f"tab:{bench}-config-comparison",
            ["Structure", "Schema", "Model", "Runs", "Success (%)", "P", "R", "F1"],
            table_rows,
            align="lllrrrrr",
        )

    write_latex_table(
        latex_dir / "model_comparison.tex",
        "Model comparison with fixed database structure and schema description.",
        "tab:model-comparison",
        ["Benchmark", "Structure", "Schema", "F1 4.1", "F1 5", "Delta F1"],
        [
            [
                row["benchmark_set"].title(),
                row["structure"].title(),
                row["schema"].title(),
                num(row["avg_f1_a"]),
                num(row["avg_f1_b"]),
                num(row["avg_f1_delta"]),
            ]
            for row in model_comparison
        ],
        align="lllrrr",
    )
    write_latex_table(
        latex_dir / "schema_description_effect.tex",
        "Effect of advanced schema descriptions compared with naive descriptions.",
        "tab:schema-description-effect",
        ["Benchmark", "Structure", "Model", "F1 naive", "F1 advanced", "Delta F1"],
        [
            [
                row["benchmark_set"].title(),
                row["structure"].title(),
                row["model"],
                num(row["avg_f1_a"]),
                num(row["avg_f1_b"]),
                num(row["avg_f1_delta"]),
            ]
            for row in schema_comparison
        ],
        align="lllrrr",
    )
    write_latex_table(
        latex_dir / "structure_effect.tex",
        "Effect of structured database design compared with flat database design.",
        "tab:structure-effect",
        ["Benchmark", "Schema", "Model", "F1 flat", "F1 structured", "Delta F1"],
        [
            [
                row["benchmark_set"].title(),
                row["schema"].title(),
                row["model"],
                num(row["avg_f1_a"]),
                num(row["avg_f1_b"]),
                num(row["avg_f1_delta"]),
            ]
            for row in structure_comparison
        ],
        align="lllrrr",
    )
    write_latex_table(
        latex_dir / "operation_performance.tex",
        "Broad query operation performance averaged across configurations.",
        "tab:operation-performance",
        ["Benchmark", "Operation", "Configs", "Questions", "Success (%)", "P", "R", "F1"],
        [
            [
                row["benchmark_set"].title(),
                row["name"].replace("_", " "),
                row["configurations"],
                num(row["questions_mean"], 1),
                pct(row["success_rate_mean"]),
                num(row["avg_precision_mean"]),
                num(row["avg_recall_mean"]),
                num(row["avg_f1_mean"]),
            ]
            for row in operation_overall
        ],
        align="llrrrrrr",
    )
    main_category_rows = [row for row in category_overall if row["benchmark_set"] == "main"]
    write_latex_table(
        latex_dir / "query_type_performance.tex",
        "Detailed query type performance on the main benchmark averaged across configurations.",
        "tab:query-type-performance",
        ["Query type", "Configs", "Questions", "Success (%)", "P", "R", "F1"],
        [
            [
                row["name"].replace("_", " "),
                row["configurations"],
                num(row["questions_mean"], 1),
                pct(row["success_rate_mean"]),
                num(row["avg_precision_mean"]),
                num(row["avg_recall_mean"]),
                num(row["avg_f1_mean"]),
            ]
            for row in main_category_rows
        ],
        align="lrrrrrr",
    )
    write_latex_table(
        latex_dir / "difficult_questions.tex",
        "Questions with the lowest average F1 across configurations.",
        "tab:difficult-questions",
        ["Benchmark", "Question", "Category", "Success (%)", "F1"],
        [
            [
                row["benchmark_set"].title(),
                f"Q{row['question_id']}",
                row["category"].replace("_", " "),
                pct(row["success_rate_mean"]),
                num(row["f1_mean"]),
            ]
            for row in difficult_questions[:12]
        ],
        align="lllrr",
    )

    write_summary_markdown(
        output_dir / "summary.md",
        runs,
        summary_rows,
        model_comparison,
        schema_comparison,
        structure_comparison,
        difficult_questions,
    )
    print(f"Wrote analysis outputs to {output_dir}")


if __name__ == "__main__":
    main()
