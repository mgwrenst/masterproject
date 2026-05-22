# Coder In The Loop

Part of a Master's project in Information Science at the University of Bergen (UiB).

This project evaluates whether an LLM can translate Norwegian natural-language questions into MongoDB queries.

## Run Evaluations

Flat database, naive schema:

```powershell
python src/text_to_query/main.py --schema src/text_to_query/schemas/flat_naive.yaml --benchmark src/text_to_query/benchmarks/flat.json --database groundtruth --label flat_naive
```

Flat database, advanced schema:

```powershell
python src/text_to_query/main.py --schema src/text_to_query/schemas/flat_advanced.yaml --benchmark src/text_to_query/benchmarks/flat.json --database groundtruth --label flat_advanced
```

Structured database, naive schema:

```powershell
python src/text_to_query/main.py --schema src/text_to_query/schemas/structured_naive.yaml --benchmark src/text_to_query/benchmarks/structured.json --database groundtruthStructured --label structured_naive
```

Structured database, advanced schema:

```powershell
python src/text_to_query/main.py --schema src/text_to_query/schemas/structured_advanced.yaml --benchmark src/text_to_query/benchmarks/structured.json --database groundtruthStructured --label structured_advanced
```

## Multiple Runs

Add `--runs` to repeat a configuration.

Example:

```powershell
python src/text_to_query/main.py --schema src/text_to_query/schemas/flat_naive.yaml --benchmark src/text_to_query/benchmarks/flat.json --database groundtruth --label flat_naive --runs 3
```

## Run One Question

Add `--id` to run one benchmark question for a configuration.

Flat naive, question 15:

```powershell
python src/text_to_query/main.py --schema src/text_to_query/schemas/flat_naive.yaml --benchmark src/text_to_query/benchmarks/flat.json --database groundtruth --label flat_naive --id 15
```

Structured naive, question 15:

```powershell
python src/text_to_query/main.py --schema src/text_to_query/schemas/structured_naive.yaml --benchmark src/text_to_query/benchmarks/structured.json --database groundtruthStructured --label structured_naive --id 15
```

Run one question three times:

```powershell
python src/text_to_query/main.py --schema src/text_to_query/schemas/flat_naive.yaml --benchmark src/text_to_query/benchmarks/flat.json --database groundtruth --label flat_naive --id 15 --runs 3
```

## Test Gold Queries

Run only the gold queries from the flat benchmark:

```powershell
python src/text_to_query/test_gold_queries.py --benchmark src/text_to_query/benchmarks/flat.json --database groundtruth
```

Run only the gold queries from the structured benchmark:

```powershell
python src/text_to_query/test_gold_queries.py --benchmark src/text_to_query/benchmarks/structured.json --database groundtruthStructured
```

Run one gold query by id:

```powershell
python src/text_to_query/test_gold_queries.py --benchmark src/text_to_query/benchmarks/flat.json --database groundtruth --id 15
```

Print example results in the terminal:

```powershell
python src/text_to_query/test_gold_queries.py --benchmark src/text_to_query/benchmarks/flat.json --database groundtruth --id 15 --show-results
```

Save the full result set:

```powershell
python src/text_to_query/test_gold_queries.py --benchmark src/text_to_query/benchmarks/flat.json --database groundtruth --id 15 --save-full
```

## Compare Results

Compare all saved evaluation result files:

```powershell
python src/text_to_query/compare.py
```

Compare selected result files:

```powershell
python src/text_to_query/compare.py "results/flat/flat_naive/20260522_120000_flat_naive.json" "results/flat/flat_advanced/20260522_120500_flat_advanced.json"
```

## Result Folders

LLM evaluation results:

```text
results/<benchmark_name>/<schema_name>/<timestamp>_<label>.json
```

Full benchmark runs include a summary, failures, and all questions. Single-question runs with `--id` save a compact file with only the run metadata and that question.

Gold-query test results:

```text
src/text_to_query/gold_results/<benchmark_name>/<timestamp>_<database>_gold_queries.json
```

## Metrics

The main metrics are precision, recall, and F1.

A question is marked successful only when both precision and recall are `1.0`.
