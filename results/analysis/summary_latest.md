# Result Analysis Summary

Generated from the latest full runs in `results/run_index.jsonl`.

## Run Overview

| Run | Success | Avg F1 | Avg Precision | Avg Recall | Errors |
|---|---:|---:|---:|---:|---:|
| flat_naive_flat_gpt-5-mini | 74.1% | 0.8299 | 0.8298 | 0.8482 | 1 |
| flat_advanced_flat_gpt-5-mini | 72.2% | 0.8331 | 0.8427 | 0.8387 | 1 |
| structured_advanced_structured_gpt-5-mini | 65.5% | 0.7494 | 0.7503 | 0.7807 | 0 |
| flat_naive_flat_gpt-4.1-mini | 63.3% | 0.7715 | 0.7802 | 0.7975 | 6 |
| structured_naive_structured_gpt-5-mini | 62.3% | 0.7759 | 0.7850 | 0.7799 | 2 |
| flat_advanced_flat_gpt-4.1-mini | 59.3% | 0.7275 | 0.7357 | 0.7509 | 1 |
| structured_naive_structured_gpt-4.1-mini | 53.7% | 0.6517 | 0.6588 | 0.6812 | 1 |
| structured_advanced_structured_gpt-4.1-mini | 49.1% | 0.6164 | 0.6171 | 0.6666 | 0 |

## Model Comparison

### flat / flat_advanced
- GPT-5 minus GPT-4.1: success rate +0.1296, avg F1 +0.1056.
- Per-question wins: GPT-5 15, GPT-4.1 6, ties 34.
- Strong GPT-5 examples: Q14 (+1), Q24 (+1), Q28 (+1), Q36 (+1), Q39 (+1).
- Strong GPT-4.1 examples: Q12 (-1), Q22 (-1), Q44 (-1), Q30 (-0.9379), Q34 (-0.8823).

### flat / flat_naive
- GPT-5 minus GPT-4.1: success rate +0.1080, avg F1 +0.0584.
- Per-question wins: GPT-5 14, GPT-4.1 4, ties 37.
- Strong GPT-5 examples: Q14 (+1), Q19 (+1), Q28 (+1), Q36 (+1), Q41 (+1).
- Strong GPT-4.1 examples: Q12 (-1), Q34 (-0.8823), Q44 (-0.7778), Q45 (-0.1514).

### structured / structured_advanced
- GPT-5 minus GPT-4.1: success rate +0.1636, avg F1 +0.1330.
- Per-question wins: GPT-5 12, GPT-4.1 3, ties 40.
- Strong GPT-5 examples: Q14 (+1), Q24 (+1), Q36 (+1), Q41 (+1), Q48 (+1).
- Strong GPT-4.1 examples: Q12 (-1), Q44 (-0.7778), Q19 (-0.0909).

### structured / structured_naive
- GPT-5 minus GPT-4.1: success rate +0.0856, avg F1 +0.1242.
- Per-question wins: GPT-5 12, GPT-4.1 6, ties 37.
- Strong GPT-5 examples: Q13 (+1), Q36 (+1), Q39 (+1), Q41 (+1), Q17 (+0.9994).
- Strong GPT-4.1 examples: Q12 (-1), Q34 (-0.8823), Q42 (-0.7784), Q44 (-0.7778), Q52 (-0.5714).

## Schema Description Comparison

### flat / gpt-4.1-mini
- Advanced minus naive: success rate -0.0401, avg F1 -0.0440.
- Per-question wins: advanced 4, naive 5, ties 46.

### flat / gpt-5-mini
- Advanced minus naive: success rate -0.0185, avg F1 +0.0032.
- Per-question wins: advanced 2, naive 4, ties 49.

### structured / gpt-4.1-mini
- Advanced minus naive: success rate -0.0461, avg F1 -0.0353.
- Per-question wins: advanced 7, naive 9, ties 39.

### structured / gpt-5-mini
- Advanced minus naive: success rate +0.0319, avg F1 -0.0265.
- Per-question wins: advanced 8, naive 7, ties 40.

## Failure Pattern Highlights

- Failed/error question-runs across all configurations: 173.
- Zero precision and zero recall with equal gold/generated counts: 50. These are good thesis cases for cardinality-correct but semantically wrong queries.
- Hardest categories by success rate: lookup_join (32.5%), aggregate_group_sum (35.0%), quantifier_exists (35.0%), aggregate_group_count (40.0%), aggregate_group_avg (47.5%).
- Slowest question-run: flat_advanced_flat_gpt-5-mini Q25 at 34208 ms.

## Files

- `overview_latest.json`: run-level metrics and weakest questions per run.
- `model_comparison_latest.json`: GPT-4.1 vs GPT-5 per matching configuration.
- `schema_comparison_latest.json`: naive vs advanced per model and structure.
- `failure_patterns_latest.json`: failures, zero-zero same-count cases, and category stats.
- `best_worst_latest.json`: best/worst runs, hardest questions, and timing extremes.
