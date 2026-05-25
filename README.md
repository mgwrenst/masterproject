# Coder In The Loop

Master's project in Information Science at the University of Bergen (UiB).

This project tests whether an LLM can translate Norwegian natural-language questions into MongoDB queries.

## Setup

Install dependencies:

```powershell
pip install -r requirements.txt
```

Set your OpenAI API key:

```powershell
$env:OPENAI_API_KEY="your_api_key"
```

Make sure MongoDB is running locally. Defaults are in [config.py](src/text_to_query/config.py).

Import the flat database, then build the structured database:

```powershell
python src/mongoDB/flat.py
```

```powershell
python src/mongoDB/structured.py --drop
```

Both database structures create indexes for common filter and lookup fields. The structured database is hybrid: it preserves full source rows in `roller`, `politikere`, `eierskap`, and `aksjeeiebok`, and adds structured `selskap` and `personer` documents with embedded summaries.

## 1. Check Gold Queries

Run and compare gold queries for both database structures:

```powershell
python src/text_to_query/test_gold_queries.py --structure both --compare
```

Refresh the gold-result cache after changing benchmark queries or reloading the database:

```powershell
python src/text_to_query/test_gold_queries.py --structure both --compare --refresh-cache
```

Run one question:

```powershell
python src/text_to_query/test_gold_queries.py --structure both --compare --id 15
```

Run and cache the complex pipeline stress benchmark:

```powershell
python src/text_to_query/test_gold_queries.py --structure both --benchmark-set complex --compare --refresh-cache
```

Gold reports are saved in `src/text_to_query/gold_results/`.
Cached gold results are saved in `src/text_to_query/gold_cache/`.

## 2. Run Evaluations

Run flat and structured benchmarks with both schema descriptions:

```powershell
python src/text_to_query/main.py --structure both --schema-version all
```

Run a single setup:

```powershell
python src/text_to_query/main.py --structure flat --schema-version naive
```

Run one question:

```powershell
python src/text_to_query/main.py --structure flat --schema-version naive --id 15
```

Compare multiple models:

```powershell
python src/text_to_query/main.py --structure both --schema-version all --models gpt-4.1-mini gpt-5-mini
```

Run the complex pipeline stress benchmark:

```powershell
python src/text_to_query/main.py --structure both --schema-version all --benchmark-set complex
```

Evaluation results are saved in `results/`.
Each run also appends one summary row to `results/run_index.jsonl`.

## Useful Options

Gold queries:

```powershell
python src/text_to_query/test_gold_queries.py --help
```

LLM evaluations:

```powershell
python src/text_to_query/main.py --help
```

Common flags:

- `--structure flat|structured|both`
- `--schema-version naive|advanced|all`
- `--benchmark-set main|complex`
- `--id 15`
- `--runs 3`
- `--model gpt-4.1-mini`
- `--models gpt-4.1-mini gpt-5-mini`
- `--refresh-cache` for gold-query cache refresh
- `--refresh-gold-cache` for evaluation cache refresh

## Compare Saved Runs

```powershell
python src/text_to_query/compare.py
```

## Analyze Saved Results

Create thesis-ready aggregate tables and key findings for both normal and complex benchmarks:

```powershell
python src/text_to_query/analyze_results.py
```

Outputs are saved in `results/analysis/`, including run summaries, category tables, per-question difficulty, comparison tables, failure cases, and a Markdown summary.

## Metrics

The main metrics are precision, recall, and F1.

A question passes when recall is `1.0`, all required projected fields are included, and precision is at least `0.5`.

Extra returned documents or fields reduce precision and F1. For direct aggregate answers, field names do not need to match as long as the values match.

If both the gold query and generated query return no results, the run treats this as full result equivalence. This is a practical evaluation choice and does not prove semantic query equivalence.
