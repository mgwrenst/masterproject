# =============================================================================
# main.py — CLI entry point for the text-to-query evaluation pipeline.
#
# Usage examples:
#   python main.py --schema schemas/simple.yaml   --benchmark benchmarks/flat.json
#   python main.py --schema schemas/advanced.yaml --benchmark benchmarks/nested.json --label nested_advanced
#   python main.py --schema schemas/simple.yaml   --benchmark benchmarks/flat.json   --threshold 0.8
# =============================================================================

import argparse
from pathlib import Path
from pipeline import run_evaluation
import config


def parse_args():
    parser = argparse.ArgumentParser(description="Text-to-Query Evaluation Pipeline")

    parser.add_argument("--schema",    required=True, help="Path to schema YAML  (e.g. schemas/simple.yaml)")
    parser.add_argument("--benchmark", required=True, help="Path to benchmark JSON (e.g. benchmarks/flat.json)")
    parser.add_argument("--label",     default=None,  help="Run label for the results file. Defaults to schema+benchmark names.")
    parser.add_argument("--threshold", type=float, default=config.DEFAULT_THRESHOLD,
                        help=f"Document precision threshold 0.0–1.0 (default: {config.DEFAULT_THRESHOLD})")
    parser.add_argument("--database", default=None,
                        help=f"MongoDB database name (default: {config.DATABASE_NAME} from config.py)")
    return parser.parse_args()


if __name__ == "__main__":
    args  = parse_args()
    label = args.label or f"{Path(args.schema).stem}_{Path(args.benchmark).stem}"
    run_evaluation(args.schema, args.benchmark, label, args.threshold, args.database)