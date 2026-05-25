import argparse
from pathlib import Path

import config
from pipeline import run_evaluation

STRUCTURE_DEFAULTS = {
    "flat": {
        "benchmarks": {
            "main": "src/text_to_query/benchmarks/flat.json",
            "complex": "src/text_to_query/benchmarks/flat_complex.json",
        },
        "database": "groundtruth",
        "schema_prefix": "flat",
    },
    "structured": {
        "benchmarks": {
            "main": "src/text_to_query/benchmarks/structured.json",
            "complex": "src/text_to_query/benchmarks/structured_complex.json",
        },
        "database": "groundtruthStructured",
        "schema_prefix": "structured",
    },
}


def parse_args():
    parser = argparse.ArgumentParser(description="Run the text-to-query evaluation pipeline")
    parser.add_argument(
        "--structure",
        choices=["flat", "structured", "both"],
        default=None,
        help="Use built-in benchmark, database, and schema paths for a database structure.",
    )
    parser.add_argument(
        "--schema-version",
        choices=["naive", "advanced", "all"],
        default="naive",
        help="Schema description version to use with --structure. Use all to run naive and advanced.",
    )
    parser.add_argument(
        "--benchmark-set",
        choices=["main", "complex"],
        default="main",
        help="Built-in benchmark set to use with --structure. Default: main.",
    )
    parser.add_argument("--schema", default=None, help="Path to schema YAML, e.g. src/text_to_query/schemas/flat_naive.yaml")
    parser.add_argument("--benchmark", default=None, help="Path to benchmark JSON, e.g. src/text_to_query/benchmarks/flat.json")
    parser.add_argument("--label", default=None, help="Result label. Defaults to schema+benchmark+model names.")
    parser.add_argument(
        "--database",
        default=None,
        help=f"MongoDB database name. Default from config.py: {config.DATABASE_NAME}",
    )
    parser.add_argument("--model", default=config.MODEL, help=f"OpenAI model to use. Default: {config.MODEL}")
    parser.add_argument(
        "--models",
        nargs="+",
        default=None,
        help=f"Run the same configuration once for each listed model. Default experiment models: {' '.join(config.MODELS)}",
    )
    parser.add_argument("--temperature", type=float, default=config.TEMPERATURE, help=f"LLM temperature. Default: {config.TEMPERATURE}")
    parser.add_argument("--max-tokens", type=int, default=config.MAX_TOKENS, help=f"Max tokens for query generation. Default: {config.MAX_TOKENS}")
    parser.add_argument("--query-max-time-ms", type=int, default=config.QUERY_MAX_TIME_MS, help=f"MongoDB maxTimeMS per query. Default: {config.QUERY_MAX_TIME_MS}")
    parser.add_argument("--no-gold-cache", action="store_true", help="Always execute gold queries instead of reading cached gold results.")
    parser.add_argument("--refresh-gold-cache", action="store_true", help="Execute gold queries and overwrite cached gold results.")
    parser.add_argument("--gold-cache-dir", default=config.GOLD_CACHE_DIR, help=f"Gold result cache directory. Default: {config.GOLD_CACHE_DIR}")
    parser.add_argument("--runs", type=int, default=1, help="Number of repeated runs with the same configuration")
    parser.add_argument("--id", type=int, default=None, help="Only run one benchmark question id")
    return parser.parse_args()


def build_jobs(args: argparse.Namespace) -> list[dict[str, str]]:
    if args.structure is None:
        if not args.schema or not args.benchmark:
            raise SystemExit("Either use --structure, or provide both --schema and --benchmark.")
        return [
            {
                "structure": Path(args.benchmark).stem,
                "schema": args.schema,
                "benchmark": args.benchmark,
                "database": args.database or config.DATABASE_NAME,
            }
        ]

    structures = ["flat", "structured"] if args.structure == "both" else [args.structure]
    schema_versions = ["naive", "advanced"] if args.schema_version == "all" else [args.schema_version]

    jobs = []
    for structure in structures:
        defaults = STRUCTURE_DEFAULTS[structure]
        for schema_version in schema_versions:
            jobs.append(
                {
                    "structure": structure,
                    "schema": f"src/text_to_query/schemas/{defaults['schema_prefix']}_{schema_version}.yaml",
                    "benchmark": defaults["benchmarks"][args.benchmark_set],
                    "database": args.database or defaults["database"],
                }
            )
    return jobs


def safe_model_label(model: str) -> str:
    return model.replace("/", "_").replace(":", "_")


def main() -> None:
    args = parse_args()
    jobs = build_jobs(args)
    models = args.models or config.MODELS

    for run_number in range(1, args.runs + 1):
        for model in models:
            for job in jobs:
                base_label = args.label or f"{Path(job['schema']).stem}_{Path(job['benchmark']).stem}_{safe_model_label(model)}"
                label_parts = [base_label]
                if len(jobs) > 1 and args.label:
                    label_parts.append(Path(job["schema"]).stem)
                if len(models) > 1 and args.label:
                    label_parts.append(safe_model_label(model))
                if args.id is not None:
                    label_parts.append(f"q{args.id}")
                if args.runs > 1:
                    label_parts.append(f"run{run_number:02d}")
                label = "_".join(label_parts)
                print(f"\nStarting run {run_number}/{args.runs}: {label}")
                run_evaluation(
                    job["schema"],
                    job["benchmark"],
                    label,
                    job["database"],
                    args.id,
                    model,
                    args.temperature,
                    args.max_tokens,
                    not args.no_gold_cache,
                    args.refresh_gold_cache,
                    args.gold_cache_dir,
                    args.query_max_time_ms,
                )


if __name__ == "__main__":
    main()
