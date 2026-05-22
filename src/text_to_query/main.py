import argparse
from pathlib import Path

import config
from pipeline import run_evaluation


def parse_args():
    parser = argparse.ArgumentParser(description="Run the text-to-query evaluation pipeline")
    parser.add_argument("--schema", required=True, help="Path to schema YAML, e.g. schemas/flat_naive.yaml")
    parser.add_argument("--benchmark", required=True, help="Path to benchmark JSON, e.g. benchmarks/flat.json")
    parser.add_argument("--label", default=None, help="Result label. Defaults to schema+benchmark names.")
    parser.add_argument(
        "--database",
        default=None,
        help=f"MongoDB database name. Default from config.py: {config.DATABASE_NAME}",
    )
    parser.add_argument("--runs", type=int, default=1, help="Number of repeated runs with the same configuration")
    parser.add_argument("--id", type=int, default=None, help="Only run one benchmark question id")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    base_label = args.label or f"{Path(args.schema).stem}_{Path(args.benchmark).stem}"

    for run_number in range(1, args.runs + 1):
        label_parts = [base_label]
        if args.id is not None:
            label_parts.append(f"q{args.id}")
        if args.runs > 1:
            label_parts.append(f"run{run_number:02d}")
        label = "_".join(label_parts)
        print(f"\nStarting run {run_number}/{args.runs}: {label}")
        run_evaluation(args.schema, args.benchmark, label, args.database, args.id)
