import json
import sys
from pathlib import Path
from typing import Any


def load_result(path: str | Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def print_run_summary(result: dict[str, Any]) -> None:
    run = result["run"]
    summary = result["summary"]
    scored = summary.get("scored_questions", summary.get("scored", 0))
    successful = summary.get("successful_questions", summary.get("matches", 0))
    success_rate = summary.get("success_rate", summary.get("match_rate", 0))
    timing = summary.get("timing_ms", {})

    print()
    print(f"{run['label']} ({run['timestamp']})")
    print(f"  model={run['model']} database={run.get('database')} schema={run['schema']} benchmark={run['benchmark']}")
    print(
        f"  success={success_rate:.1%} "
        f"({successful}/{scored}) "
        f"P={summary['avg_precision']:.4f} "
        f"R={summary['avg_recall']:.4f} "
        f"F1={summary['avg_f1']:.4f}"
    )
    if timing:
        print(f"  time={timing.get('total_run')}ms total, {timing.get('avg_per_question')}ms/question")

    if summary["errors"]["total"]:
        print(f"  errors={summary['errors']}")

    print("  by operation:")
    by_operation = summary.get("by_operation", summary.get("by_op", {}))
    for operation, values in by_operation.items():
        questions = values.get("questions", values.get("n", 0))
        op_success_rate = values.get("success_rate", values.get("match_rate", 0))
        print(
            f"    {operation:<10} "
            f"success={op_success_rate:.1%} "
            f"F1={values['avg_f1']:.4f} "
            f"n={questions}"
        )


def print_failure_list(result: dict[str, Any], limit: int = 10) -> None:
    failures = result.get("failures")
    if failures is None:
        failures = [
            question for question in result.get("questions", [])
            if not question.get("match", question.get("success", False))
        ]
    failures = failures[:limit]
    if not failures:
        print("  no failures")
        return

    print("  failures:")
    for failure in failures:
        scores = failure.get("scores") or {}
        f1 = scores.get("f1")
        f1_text = f"F1={f1:.2f}" if isinstance(f1, (int, float)) else failure["status"]
        print(f"    Q{failure['id']}: {f1_text} - {failure['question'][:80]}")
        reason = failure.get("failure_reason") or failure.get("error")
        if reason:
            print(f"      {reason}")


def compare_questions(results: list[dict[str, Any]]) -> None:
    labels = [result["run"]["label"] for result in results]
    question_ids = sorted(
        {
            question["id"]
            for result in results
            for question in result.get("questions", [])
        },
        key=lambda value: str(value),
    )

    index = {
        result["run"]["label"]: {
            question["id"]: question
            for question in result.get("questions", [])
        }
        for result in results
    }

    print()
    print("=" * 100)
    print("Per-question comparison")
    print("=" * 100)
    print(f"{'ID':<5} {'Question':<54} " + "  ".join(f"{label[:16]:<16}" for label in labels))
    print(f"{'-' * 5} {'-' * 54} " + "  ".join("-" * 16 for _ in labels))

    for question_id in question_ids:
        question_text = ""
        columns = []
        for label in labels:
            question = index[label].get(question_id)
            if not question:
                columns.append("N/A".ljust(16))
                continue

            question_text = question["question"][:54]
            if question["status"] != "ok":
                columns.append(("ERR " + question["status"])[:16].ljust(16))
                continue

            score = question["scores"]
            prefix = "OK" if question.get("success", question.get("match", False)) else "NO"
            columns.append(f"{prefix} F1={score['f1']:.2f}".ljust(16))

        print(f"{str(question_id):<5} {question_text:<54} " + "  ".join(columns))


def main() -> None:
    paths = sys.argv[1:] if len(sys.argv) > 1 else sorted(Path("results").rglob("*.json"))
    if not paths:
        print("No result files found.")
        return

    results = [load_result(path) for path in paths]

    print()
    print("=" * 72)
    print(f"Evaluation comparison ({len(results)} run(s))")
    print("=" * 72)

    for result in results:
        print_run_summary(result)
        print_failure_list(result)

    if len(results) > 1:
        compare_questions(results)


if __name__ == "__main__":
    main()
