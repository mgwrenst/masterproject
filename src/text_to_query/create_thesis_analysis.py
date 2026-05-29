import argparse
import csv
import json
import math
import shutil
from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev
from typing import Any


METRICS = ("precision", "recall", "f1", "runtime_s")
MODELS = ("gpt-4.1-mini", "gpt-5-mini")
BENCHMARK_ORDER = {"standard": 0, "complex": 1}
STRUCTURE_ORDER = {"flat": 0, "structured": 1}
SCHEMA_ORDER = {"naive": 0, "technical": 1}
MODEL_ORDER = {"gpt-4.1-mini": 0, "gpt-5-mini": 1}


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def benchmark_type(run: dict[str, Any]) -> str:
    benchmark = str(run.get("benchmark", "")).lower()
    return "complex" if "complex" in benchmark else "standard"


def structure_name(run: dict[str, Any]) -> str:
    benchmark = str(run.get("benchmark", "")).lower()
    structure = str(run.get("structure") or "").lower()
    combined = f"{benchmark} {structure}"
    return "structured" if "structured" in combined else "flat"


def schema_name(run: dict[str, Any]) -> str:
    schema = Path(str(run.get("schema", ""))).stem.lower()
    return "technical" if "advanced" in schema or "technical" in schema else "naive"


def display_title(value: str) -> str:
    replacements = {
        "standard": "Standard",
        "complex": "Complex",
        "flat": "Flat",
        "structured": "Structured",
        "naive": "Naive",
        "technical": "Technical",
        "gpt-4.1-mini": "GPT-4.1-mini",
        "gpt-5-mini": "GPT-5-mini",
    }
    return replacements.get(value, value.replace("_", " ").title())


def repair_mojibake(value: Any) -> str:
    text = str(value)
    if "Ã" not in text and "Â" not in text:
        return text
    try:
        return text.encode("latin-1").decode("utf-8")
    except UnicodeError:
        return text


def load_runs(results_dir: Path) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for path in sorted(results_dir.rglob("*.json")):
        if "analysis" in path.parts:
            continue
        data = load_json(path)
        if "run" not in data or "summary" not in data:
            continue
        run = data["run"]
        summary = data["summary"]
        runs.append(
            {
                "path": str(path),
                "timestamp": run.get("timestamp", ""),
                "label": run.get("label", path.stem),
                "benchmark": benchmark_type(run),
                "structure": structure_name(run),
                "schema": schema_name(run),
                "model": run.get("model", ""),
                "questions": summary.get("total_questions", 0),
                "scored_questions": summary.get("scored_questions", summary.get("total_questions", 0)),
                "successful_questions": summary.get("successful_questions", 0),
                "success_rate": summary.get("success_rate", 0.0),
                "precision": summary.get("avg_precision", 0.0),
                "recall": summary.get("avg_recall", 0.0),
                "f1": summary.get("avg_f1", 0.0),
                "runtime_s": summary.get("timing_ms", {}).get("avg_per_question", 0.0) / 1000,
                "error_total": summary.get("errors", {}).get("total", 0),
                "by_operation": summary.get("by_operation", {}),
                "by_category": summary.get("by_category", {}),
                "questions_data": data.get("questions", []),
            }
        )
    return runs


def metric_stats(values: list[float]) -> tuple[float, float]:
    if not values:
        return math.nan, math.nan
    return mean(values), stdev(values) if len(values) > 1 else 0.0


def aggregate_runs(runs: list[dict[str, Any]], group_fields: tuple[str, ...]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for run in runs:
        grouped[tuple(run[field] for field in group_fields)].append(run)

    rows: list[dict[str, Any]] = []
    for key, items in grouped.items():
        row = dict(zip(group_fields, key, strict=True))
        row["runs"] = len(items)
        row["questions_per_run"] = mean(item["questions"] for item in items)
        row["errors_mean"] = mean(item["error_total"] for item in items)
        for metric in ("success_rate", *METRICS):
            avg, sd = metric_stats([item[metric] for item in items])
            row[f"{metric}_mean"] = avg
            row[f"{metric}_std"] = sd
        rows.append(row)
    return rows


def aggregate_summary_rows(rows: list[dict[str, Any]], group_fields: tuple[str, ...]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[tuple(row[field] for field in group_fields)].append(row)

    output: list[dict[str, Any]] = []
    for key, items in grouped.items():
        row = dict(zip(group_fields, key, strict=True))
        row["configurations"] = len(items)
        row["runs"] = sum(item["runs"] for item in items)
        for metric in ("success_rate", *METRICS):
            avg, sd = metric_stats([item[f"{metric}_mean"] for item in items])
            row[f"{metric}_mean"] = avg
            row[f"{metric}_std"] = sd
        output.append(row)
    return output


def nested_rows(runs: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for run in runs:
        for name, data in run[field].items():
            key = (run["benchmark"], run["structure"], run["schema"], run["model"], name)
            grouped[key].append(data)

    rows: list[dict[str, Any]] = []
    for (benchmark, structure, schema, model, name), items in grouped.items():
        row = {
            "benchmark": benchmark,
            "structure": structure,
            "schema": schema,
            "model": model,
            "name": name,
            "runs": len(items),
            "questions_mean": mean(item.get("questions", 0) for item in items),
        }
        for metric, source in (
            ("success_rate", "success_rate"),
            ("precision", "avg_precision"),
            ("recall", "avg_recall"),
            ("f1", "avg_f1"),
        ):
            avg, sd = metric_stats([item.get(source, 0.0) for item in items])
            row[f"{metric}_mean"] = avg
            row[f"{metric}_std"] = sd
        rows.append(row)
    return rows


def aggregate_nested(rows: list[dict[str, Any]], group_fields: tuple[str, ...]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[tuple(row[field] for field in group_fields)].append(row)

    output: list[dict[str, Any]] = []
    for key, items in grouped.items():
        row = dict(zip(group_fields, key, strict=True))
        row["configurations"] = len(items)
        row["questions_mean"] = mean(item["questions_mean"] for item in items)
        for metric in ("success_rate", "precision", "recall", "f1"):
            avg, sd = metric_stats([item[f"{metric}_mean"] for item in items])
            row[f"{metric}_mean"] = avg
            row[f"{metric}_std"] = sd
        output.append(row)
    return output


def question_difficulty(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, Any], list[dict[str, Any]]] = defaultdict(list)
    meta: dict[tuple[str, Any], dict[str, Any]] = {}
    for run in runs:
        for question in run["questions_data"]:
            scores = question.get("scores") or {}
            key = (run["benchmark"], question.get("id"))
            grouped[key].append(
                {
                    "success": 1.0 if question.get("success") else 0.0,
                    "precision": scores.get("precision", 0.0),
                    "recall": scores.get("recall", 0.0),
                    "f1": scores.get("f1", 0.0),
                    "error": 0.0 if question.get("status") == "ok" else 1.0,
                }
            )
            meta[key] = {
                "question": repair_mojibake(question.get("question", "")),
                "category": question.get("category", ""),
                "operation": question.get("operation", ""),
            }

    rows: list[dict[str, Any]] = []
    for key, items in grouped.items():
        row = {
            "benchmark": key[0],
            "question_id": key[1],
            **meta[key],
            "observations": len(items),
            "success_rate_mean": mean(item["success"] for item in items),
            "precision_mean": mean(item["precision"] for item in items),
            "recall_mean": mean(item["recall"] for item in items),
            "f1_mean": mean(item["f1"] for item in items),
            "error_runs": sum(item["error"] for item in items),
        }
        rows.append(row)
    return sorted(rows, key=lambda row: (BENCHMARK_ORDER[row["benchmark"]], row["f1_mean"], row["success_rate_mean"], row["question_id"]))


def pct(value: float) -> str:
    return "--" if math.isnan(value) else f"{value * 100:.1f}"


def num(value: float, digits: int = 3) -> str:
    return "--" if math.isnan(value) else f"{value:.{digits}f}"


def tex_num(value: float, best: bool = False, digits: int = 3) -> str:
    text = num(value, digits)
    return rf"\textbf{{{text}}}" if best else text


def tex_pct(value: float, best: bool = False) -> str:
    text = pct(value)
    return rf"\textbf{{{text}}}" if best else text


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
    align: str,
    notes: str | None = None,
) -> None:
    lines = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\small",
        rf"\caption{{{latex_escape(caption)}}}",
        rf"\label{{{label}}}",
        rf"\begin{{tabular}}{{{align}}}",
        r"\toprule",
        " & ".join(latex_escape(header) for header in headers) + r" \\",
        r"\midrule",
    ]
    for row in rows:
        cells = [str(cell) if str(cell).startswith(r"\textbf") else latex_escape(cell) for cell in row]
        lines.append(" & ".join(cells) + r" \\")
    lines.extend([r"\bottomrule", r"\end{tabular}"])
    if notes:
        lines.append(rf"\par\footnotesize{{{latex_escape(notes)}}}")
    lines.extend([r"\end{table}", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sort_config(row: dict[str, Any]) -> tuple[int, int, int, int]:
    return (
        BENCHMARK_ORDER[row["benchmark"]],
        STRUCTURE_ORDER[row["structure"]],
        SCHEMA_ORDER[row["schema"]],
        MODEL_ORDER[row["model"]],
    )


def config_label(row: dict[str, Any], include_benchmark: bool = False) -> str:
    parts = []
    if include_benchmark:
        parts.append(display_title(row["benchmark"]))
    parts.extend([display_title(row["structure"]), display_title(row["schema"]), display_title(row["model"])])
    return " + ".join(parts)


def find_best(rows: list[dict[str, Any]], metric: str) -> float:
    return max(row[f"{metric}_mean"] for row in rows)


def write_tables(output_dir: Path, config_rows: list[dict[str, Any]], operation_rows: list[dict[str, Any]], category_rows: list[dict[str, Any]], difficult_rows: list[dict[str, Any]]) -> None:
    latex_dir = output_dir / "tables"
    latex_dir.mkdir(parents=True, exist_ok=True)

    sorted_configs = sorted(config_rows, key=sort_config)
    best = {metric: find_best(sorted_configs, metric) for metric in ("precision", "recall", "f1")}
    best["runtime_s"] = min(row["runtime_s_mean"] for row in sorted_configs)
    overall_rows = [
        [
            display_title(row["benchmark"]),
            config_label(row),
            row["runs"],
            tex_num(row["precision_mean"], row["precision_mean"] == best["precision"]),
            tex_num(row["recall_mean"], row["recall_mean"] == best["recall"]),
            tex_num(row["f1_mean"], row["f1_mean"] == best["f1"]),
            tex_num(row["runtime_s_mean"], row["runtime_s_mean"] == best["runtime_s"], digits=2),
        ]
        for row in sorted_configs
    ]
    write_latex_table(
        latex_dir / "overall_configuration_summary.tex",
        "Complete configuration overview.",
        "tab:overall-configuration-summary",
        ["Benchmark", "Configuration", "Runs", "Precision", "Recall", "F1", "Runtime (s)"],
        overall_rows,
        align="llrrrrr",
        notes="Values are means across three runs. This table is intended for the appendix if it is too dense for the main results chapter.",
    )

    rows = aggregate_summary_rows([row for row in config_rows if row["benchmark"] == "standard"], ("schema",))
    rows = sorted(rows, key=lambda row: SCHEMA_ORDER[row["schema"]])
    schema_table_rows = [[display_title(row["schema"]), num(row["precision_mean"]), num(row["recall_mean"]), num(row["f1_mean"])] for row in rows]
    write_latex_table(
        latex_dir / "schema_description_standard.tex",
        "Naive versus technical schema description performance on the standard benchmark.",
        "tab:schema-description-standard",
        ["Description type", "Precision", "Recall", "F1"],
        schema_table_rows,
        align="lrrr",
        notes="Values are averaged across database structures and models.",
    )

    rows = aggregate_summary_rows([row for row in config_rows if row["benchmark"] == "standard"], ("model",))
    rows = sorted(rows, key=lambda row: MODEL_ORDER[row["model"]])
    model_table_rows = [[display_title(row["model"]), num(row["precision_mean"]), num(row["recall_mean"]), num(row["f1_mean"]), num(row["runtime_s_mean"], 2)] for row in rows]
    write_latex_table(
        latex_dir / "model_comparison_standard.tex",
        "Model comparison on the standard benchmark.",
        "tab:model-comparison-standard",
        ["Model", "Precision", "Recall", "F1", "Runtime (s)"],
        model_table_rows,
        align="lrrrr",
        notes="Values are averaged across database structures and schema descriptions.",
    )

    standard_rows = aggregate_summary_rows([row for row in config_rows if row["benchmark"] == "standard"], ("structure", "model"))
    standard_rows = sorted(standard_rows, key=lambda row: (MODEL_ORDER[row["model"]], STRUCTURE_ORDER[row["structure"]]))
    database_standard_rows = [[display_title(row["model"]), display_title(row["structure"]), num(row["precision_mean"]), num(row["recall_mean"]), num(row["f1_mean"])] for row in standard_rows]
    write_latex_table(
        latex_dir / "database_structure_standard.tex",
        "Flat versus structured database performance on the standard benchmark.",
        "tab:database-structure-standard",
        ["Model", "Structure", "Precision", "Recall", "F1"],
        database_standard_rows,
        align="llrrr",
        notes="Values are averaged across naive and technical schema descriptions.",
    )

    complex_rows = aggregate_summary_rows([row for row in config_rows if row["benchmark"] == "complex"], ("structure", "model"))
    complex_rows = sorted(complex_rows, key=lambda row: (MODEL_ORDER[row["model"]], STRUCTURE_ORDER[row["structure"]]))
    database_complex_rows = [[display_title(row["model"]), display_title(row["structure"]), num(row["precision_mean"]), num(row["recall_mean"]), num(row["f1_mean"])] for row in complex_rows]
    write_latex_table(
        latex_dir / "database_structure_complex.tex",
        "Flat versus structured database performance on the complex benchmark.",
        "tab:database-structure-complex",
        ["Model", "Structure", "Precision", "Recall", "F1"],
        database_complex_rows,
        align="llrrr",
        notes="Values are averaged across naive and technical schema descriptions.",
    )

    rows = aggregate_summary_rows(config_rows, ("benchmark",))
    rows = sorted(rows, key=lambda row: BENCHMARK_ORDER[row["benchmark"]])
    benchmark_table_rows = [[display_title(row["benchmark"]), num(row["precision_mean"]), num(row["recall_mean"]), num(row["f1_mean"]), num(row["runtime_s_mean"], 2)] for row in rows]
    write_latex_table(
        latex_dir / "standard_complex_overview.tex",
        "Standard versus complex benchmark performance.",
        "tab:standard-complex-overview",
        ["Benchmark type", "Precision", "Recall", "F1", "Runtime (s)"],
        benchmark_table_rows,
        align="lrrrr",
        notes="Values are averaged across all configurations within each benchmark type.",
    )

    rows = sorted(config_rows, key=sort_config)
    runtime_table_rows = [[display_title(row["benchmark"]), display_title(row["structure"]), display_title(row["schema"]), display_title(row["model"]), num(row["runtime_s_mean"], 2), num(row["runtime_s_std"], 2)] for row in rows]
    write_latex_table(
        latex_dir / "runtime.tex",
        "Average runtime per question by configuration.",
        "tab:runtime",
        ["Benchmark", "Structure", "Schema", "Model", "Avg runtime (s)", "Runtime SD"],
        runtime_table_rows,
        align="llllrr",
        notes="Runtime is measured as average wall-clock time per benchmark question. Runtime SD is the standard deviation across the three repeated runs for the same configuration.",
    )

    op_rows = aggregate_nested(operation_rows, ("benchmark", "name"))
    op_rows = sorted(op_rows, key=lambda row: (BENCHMARK_ORDER[row["benchmark"]], -row["f1_mean"], row["name"]))
    operation_table_rows = [[display_title(row["benchmark"]), display_title(row["name"]), num(row["precision_mean"]), num(row["recall_mean"]), num(row["f1_mean"])] for row in op_rows]
    write_latex_table(
        latex_dir / "operation_type_performance.tex",
        "Performance by MongoDB operation type.",
        "tab:operation-type-performance",
        ["Benchmark", "Operation", "Precision", "Recall", "F1"],
        operation_table_rows,
        align="llrrr",
        notes="Values are averaged across configurations containing each operation type.",
    )

    cat_rows = aggregate_nested(category_rows, ("benchmark", "name"))
    cat_rows = sorted(cat_rows, key=lambda row: (BENCHMARK_ORDER[row["benchmark"]], -row["f1_mean"], row["name"]))
    category_table_rows = [[display_title(row["benchmark"]), display_title(row["name"]), num(row["precision_mean"]), num(row["recall_mean"]), num(row["f1_mean"])] for row in cat_rows]
    write_latex_table(
        latex_dir / "query_category_performance.tex",
        "Performance by query category.",
        "tab:query-category-performance",
        ["Benchmark", "Query type", "Precision", "Recall", "F1"],
        category_table_rows,
        align="llrrr",
        notes="Values are averaged across configurations containing each query category.",
    )

    difficult_table_rows = [[display_title(row["benchmark"]), f"Q{row['question_id']}", display_title(row["operation"]), display_title(row["category"]), pct(row["success_rate_mean"]), num(row["f1_mean"])] for row in difficult_rows[:12]]
    write_latex_table(
        latex_dir / "lowest_scoring_questions.tex",
        "Lowest-scoring benchmark questions across configurations.",
        "tab:lowest-scoring-questions",
        ["Benchmark", "Question", "Operation", "Category", "Success (%)", "F1"],
        difficult_table_rows,
        align="llllrr",
        notes="Rows are ranked by mean F1 across all runs and configurations for the benchmark.",
    )

    write_latex_table(
        latex_dir / "f1_stability_by_configuration.tex",
        "F1-score stability across repeated runs.",
        "tab:f1-stability",
        ["Benchmark", "Configuration", "Mean F1", "F1 SD"],
        [[display_title(row["benchmark"]), config_label(row), num(row["f1_mean"]), num(row["f1_std"])] for row in sorted_configs],
        align="llrr",
        notes="Standard deviation is computed over the three runs for each configuration.",
    )

    write_latex_table(
        latex_dir / "review_requirement_guidance.tex",
        "Suggested review level by query type.",
        "tab:review-requirement-guidance",
        ["Query type", "Observed reliability", "Suggested review level"],
        [
            ["Distinct", "High", "Journalist can use independently"],
            ["Find / projection", "High", "Journalist can use independently"],
            ["Simple aggregation", "Medium", "Review recommended"],
            ["Lookup join", "Low/medium", "Coder review required"],
            ["Quantifier exists", "Low/medium", "Coder review required"],
            ["Group sum / complex pipeline", "Low", "Coder review required"],
        ],
        align="lll",
        notes="This table is interpretive and is intended for the discussion chapter rather than the descriptive results chapter.",
    )


def largest_difference(rows: list[dict[str, Any]], field: str) -> tuple[str, float]:
    grouped: dict[tuple[Any, ...], dict[str, dict[str, Any]]] = defaultdict(dict)
    compare_values = {"structure": ("flat", "structured"), "schema": ("naive", "technical"), "model": MODELS}[field]
    other_fields = [name for name in ("benchmark", "structure", "schema", "model") if name != field]
    for row in rows:
        grouped[tuple(row[name] for name in other_fields)][row[field]] = row

    best_label = ""
    best_delta = 0.0
    for key, values in grouped.items():
        if compare_values[0] not in values or compare_values[1] not in values:
            continue
        delta = values[compare_values[1]]["f1_mean"] - values[compare_values[0]]["f1_mean"]
        if abs(delta) >= abs(best_delta):
            context = ", ".join(display_title(str(value)) for value in key)
            best_label = context
            best_delta = delta
    return best_label, best_delta


def write_summary(output_dir: Path, runs: list[dict[str, Any]], config_rows: list[dict[str, Any]], difficult_rows: list[dict[str, Any]]) -> None:
    standard = [row for row in config_rows if row["benchmark"] == "standard"]
    complex_rows = [row for row in config_rows if row["benchmark"] == "complex"]
    best_standard = max(standard, key=lambda row: row["f1_mean"])
    best_complex = max(complex_rows, key=lambda row: row["f1_mean"])
    benchmark_summary = {row["benchmark"]: row for row in aggregate_summary_rows(config_rows, ("benchmark",))}
    model_summary = {row["model"]: row for row in aggregate_summary_rows(standard, ("model",))}
    structure_summary = {row["structure"]: row for row in aggregate_summary_rows(standard, ("structure",))}
    schema_summary = {row["schema"]: row for row in aggregate_summary_rows(standard, ("schema",))}
    runtime_summary = aggregate_summary_rows(config_rows, ("benchmark", "model"))

    lines = [
        "# Thesis Results Summary",
        "",
        "## Methodological framing",
        "",
        f"The analysis is based on {len(runs)} saved evaluation runs. Each configuration was executed three times, and the values reported in the tables are arithmetic means across those repetitions. Precision, recall, and F1-score were computed over returned result values, while runtime represents the average wall-clock time per benchmark question. The standard benchmark contains the main text-to-query tasks, whereas the complex benchmark isolates aggregation-heavy pipeline questions.",
        "",
        "## Overall performance",
        "",
        f"The strongest standard-benchmark configuration was {config_label(best_standard)}, with mean precision {num(best_standard['precision_mean'])}, recall {num(best_standard['recall_mean'])}, and F1-score {num(best_standard['f1_mean'])}. On the complex benchmark, the strongest configuration was {config_label(best_complex)}, with mean precision {num(best_complex['precision_mean'])}, recall {num(best_complex['recall_mean'])}, and F1-score {num(best_complex['f1_mean'])}. Across all configurations, the standard benchmark reached a mean F1-score of {num(benchmark_summary['standard']['f1_mean'])}, while the complex benchmark reached {num(benchmark_summary['complex']['f1_mean'])}. This indicates a substantial performance drop when the task requires more complex aggregation logic.",
        "",
        "## Effect of database structure",
        "",
        f"On the standard benchmark, the flat database representation produced a mean F1-score of {num(structure_summary['flat']['f1_mean'])}, compared with {num(structure_summary['structured']['f1_mean'])} for the structured representation. The flat representation also produced higher mean precision ({num(structure_summary['flat']['precision_mean'])} versus {num(structure_summary['structured']['precision_mean'])}) and recall ({num(structure_summary['flat']['recall_mean'])} versus {num(structure_summary['structured']['recall_mean'])}). In this experiment, the denormalized flat schema therefore appears easier for the models to translate into executable MongoDB queries.",
        "",
        "## Effect of schema description",
        "",
        f"The naive schema descriptions reached a mean standard-benchmark F1-score of {num(schema_summary['naive']['f1_mean'])}, while the technical schema descriptions reached {num(schema_summary['technical']['f1_mean'])}. The difference is small, suggesting that more technical schema detail did not consistently improve output quality in this setup. This should be interpreted carefully because technical descriptions can help with precise field use, but may also increase prompt complexity and distract the model from the user intent.",
        "",
        "## Model comparison",
        "",
        f"GPT-5-mini outperformed GPT-4.1-mini on the standard benchmark. GPT-4.1-mini obtained mean precision {num(model_summary['gpt-4.1-mini']['precision_mean'])}, recall {num(model_summary['gpt-4.1-mini']['recall_mean'])}, and F1-score {num(model_summary['gpt-4.1-mini']['f1_mean'])}; GPT-5-mini obtained mean precision {num(model_summary['gpt-5-mini']['precision_mean'])}, recall {num(model_summary['gpt-5-mini']['recall_mean'])}, and F1-score {num(model_summary['gpt-5-mini']['f1_mean'])}. The improvement is therefore visible in both retrieval completeness and result precision.",
        "",
        "## Complex query benchmark",
        "",
        f"The complex benchmark was substantially more difficult than the standard benchmark. The mean F1-score decreased from {num(benchmark_summary['standard']['f1_mean'])} on standard questions to {num(benchmark_summary['complex']['f1_mean'])} on complex questions. This decline is consistent with the increased difficulty of generating multi-stage aggregation pipelines, where errors in joins, grouping keys, unwinding, filtering order, or projection logic can cause large deviations in the final result set.",
        "",
        "## Runtime analysis",
        "",
    ]
    for row in sorted(runtime_summary, key=lambda row: (BENCHMARK_ORDER[row["benchmark"]], MODEL_ORDER[row["model"]])):
        lines.append(f"- {display_title(row['benchmark'])} / {display_title(row['model'])}: mean runtime {num(row['runtime_s_mean'], 2)} seconds per question.")
    lines.extend(
        [
            "",
            "The runtime results should be discussed as latency rather than computational complexity. They include LLM response time, generated query execution, and scoring overhead. Differences between models therefore reflect both model latency and the interaction between generated query shape and MongoDB execution.",
            "",
            "## Lowest-performing questions",
            "",
            "The most difficult questions were dominated by tasks requiring cross-entity reasoning or complex aggregation. These questions often require the generated query to preserve several constraints simultaneously, such as matching people to parties, combining role counts with ownership counts, or maintaining correct grouping semantics after array unwinding.",
            "",
        ]
    )
    for row in difficult_rows[:8]:
        question = row["question"].replace("\n", " ")
        lines.append(f"- {display_title(row['benchmark'])} Q{row['question_id']}: F1 {num(row['f1_mean'])}, success {pct(row['success_rate_mean'])}%. {question}")
    lines.append("")
    output_dir.joinpath("results_summary.md").write_text("\n".join(lines), encoding="utf-8")


def write_discussion_points(output_dir: Path, config_rows: list[dict[str, Any]], difficult_rows: list[dict[str, Any]]) -> None:
    structure_context, structure_delta = largest_difference(config_rows, "structure")
    schema_context, schema_delta = largest_difference(config_rows, "schema")
    model_context, model_delta = largest_difference(config_rows, "model")
    lines = [
        "# Discussion Chapter Notes",
        "",
        "## Database representation and query generation",
        "",
        f"The strongest structure-related F1 difference was {num(structure_delta)} in the context of {structure_context}. This can be discussed in relation to schema linking, denormalization, and the cost of reasoning over embedded or referenced structures. Relevant literature areas include text-to-SQL/text-to-query schema linking, database normalization versus denormalization, and prompt grounding for structured data.",
        "",
        "Potential citation areas: schema linking in neural semantic parsing; effects of database schema complexity on query synthesis; MongoDB document modeling and denormalization trade-offs.",
        "",
        "## Prompt detail and schema descriptions",
        "",
        f"The strongest schema-description F1 difference was {num(schema_delta)} in the context of {schema_context}. The results can support a discussion of whether additional technical metadata improves grounding or instead increases prompt load. This is a useful place to cite work on prompt specificity, context length, instruction following, and schema serialization for language models.",
        "",
        "Potential citation areas: prompt engineering for code generation; schema serialization in text-to-SQL systems; cognitive load or irrelevant context in long prompts.",
        "",
        "## Model capability differences",
        "",
        f"The strongest model-related F1 difference was {num(model_delta)} in the context of {model_context}. This can be discussed as evidence that model capability matters for query generation, especially when the task requires multi-step reasoning, operator selection, and precise syntax generation.",
        "",
        "Potential citation areas: LLMs for code generation; LLMs for semantic parsing; benchmark studies comparing model families on structured-query generation.",
        "",
        "## Complex aggregation pipelines",
        "",
        "The complex benchmark produced much lower average F1 than the standard benchmark. This should be discussed as a robustness issue: aggregation pipelines are brittle because each stage depends on the correctness of earlier stages. A query can be syntactically valid while still using an incorrect grouping key, losing documents during unwinding, applying filters in the wrong order, or projecting fields that do not preserve the target answer.",
        "",
        "Potential citation areas: compositional generalization in semantic parsing; multi-hop reasoning in LLMs; MongoDB aggregation pipeline semantics; execution-guided query generation.",
        "",
        "## Evaluation metric limitations",
        "",
        "Precision, recall, and F1 were computed over returned values rather than over query syntax. This is appropriate because semantically different MongoDB queries can produce equivalent result sets. However, result-equivalence scoring also has limits: equivalent outputs do not prove equivalent query semantics, and empty result sets can overstate correctness if both gold and generated queries return nothing.",
        "",
        "Potential citation areas: execution accuracy in semantic parsing; denotation-based evaluation; limitations of exact-match metrics for query generation.",
        "",
        "## Runtime and usability",
        "",
        "Runtime should be interpreted as end-to-end latency from the perspective of an application user. Higher F1 may be worth additional latency in analytical settings, while interactive systems may require stricter response-time constraints. Runtime differences can also reflect generated query efficiency, not only model response latency.",
        "",
        "Potential citation areas: human-computer interaction latency thresholds; LLM application latency; database query optimization and generated query efficiency.",
        "",
        "## Stability across repeated runs",
        "",
        "Because each configuration was run three times, standard deviation can be used to discuss stochastic stability. Low standard deviation strengthens confidence that the observed trends are not isolated generations. Larger deviations indicate configurations where the model is less reliable even if the mean score is acceptable.",
        "",
        "Potential citation areas: nondeterminism in LLM outputs; reproducibility of LLM evaluations; statistical reporting for empirical software engineering.",
        "",
        "## Threats to validity",
        "",
        "Useful threats to validity include benchmark size, domain specificity, Norwegian-language questions, dependence on one MongoDB dataset, result-equivalence scoring, limited number of repeated runs, and the possibility that prompt templates favor one schema representation over another.",
        "",
        "Potential citation areas: internal/external validity in empirical software engineering; dataset bias in semantic parsing; multilingual LLM performance.",
        "",
        "## Specific difficult-question patterns",
        "",
    ]
    for row in difficult_rows[:10]:
        lines.append(f"- {display_title(row['benchmark'])} Q{row['question_id']} ({display_title(row['operation'])}, {display_title(row['category'])}): mean F1 {num(row['f1_mean'])}.")
    lines.append("")
    output_dir.joinpath("discussion_points.md").write_text("\n".join(lines), encoding="utf-8")


def write_csv_outputs(output_dir: Path, runs: list[dict[str, Any]], config_rows: list[dict[str, Any]], operation_rows: list[dict[str, Any]], category_rows: list[dict[str, Any]], difficult_rows: list[dict[str, Any]]) -> None:
    csv_dir = output_dir / "csv"
    write_csv(csv_dir / "run_level_results.csv", runs, ["timestamp", "label", "benchmark", "structure", "schema", "model", "questions", "successful_questions", "success_rate", "precision", "recall", "f1", "runtime_s", "error_total", "path"])
    write_csv(csv_dir / "configuration_means.csv", config_rows, ["benchmark", "structure", "schema", "model", "runs", "questions_per_run", "success_rate_mean", "success_rate_std", "precision_mean", "precision_std", "recall_mean", "recall_std", "f1_mean", "f1_std", "runtime_s_mean", "runtime_s_std", "errors_mean"])
    write_csv(csv_dir / "operation_means.csv", operation_rows, ["benchmark", "structure", "schema", "model", "name", "runs", "questions_mean", "success_rate_mean", "success_rate_std", "precision_mean", "precision_std", "recall_mean", "recall_std", "f1_mean", "f1_std"])
    write_csv(csv_dir / "category_means.csv", category_rows, ["benchmark", "structure", "schema", "model", "name", "runs", "questions_mean", "success_rate_mean", "success_rate_std", "precision_mean", "precision_std", "recall_mean", "recall_std", "f1_mean", "f1_std"])
    write_csv(csv_dir / "question_difficulty.csv", difficult_rows, ["benchmark", "question_id", "operation", "category", "observations", "success_rate_mean", "precision_mean", "recall_mean", "f1_mean", "error_runs", "question"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate thesis-oriented analysis tables and prose from evaluation results.")
    parser.add_argument("--results-dir", default="results")
    parser.add_argument("--output-dir", default="results/analysis")
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    output_dir = Path(args.output_dir)
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    runs = load_runs(results_dir)
    if not runs:
        raise SystemExit(f"No result files found below {results_dir}")

    config_rows = aggregate_runs(runs, ("benchmark", "structure", "schema", "model"))
    operation_rows = nested_rows(runs, "by_operation")
    category_rows = nested_rows(runs, "by_category")
    difficult_rows = question_difficulty(runs)

    write_tables(output_dir, config_rows, operation_rows, category_rows, difficult_rows)
    write_csv_outputs(output_dir, runs, config_rows, operation_rows, category_rows, difficult_rows)
    write_summary(output_dir, runs, config_rows, difficult_rows)
    write_discussion_points(output_dir, config_rows, difficult_rows)
    print(f"Wrote thesis analysis to {output_dir}")


if __name__ == "__main__":
    main()
