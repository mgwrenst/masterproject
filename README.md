# Coder In The Loop
> Part of a Master’s project in Information Science at the University of Bergen (UiB).

Evaluating whether an LLM can reliably translate **Norwegian natural-language questions** into **MongoDB queries**, enabling journalists to explore databases without technical knowledge

---

## Background

Journalists often need data from databases but lack the technical skills to write queries. This projects tests whether LLMs can bridge that gap - turning editorial questions into correct, executable MongoDB queries (MQL).

## Scope

- Norwegian natural language → MongoDB Query Langauge (MQL)
- Evaluation against a local MongoDB instance
- Metrics: precsision, recall, F1

## Tech stack

- Python — pipeline and evaluation scripts
- MongoDB — local database instance
- MongoDB Compass — local DB setup and inspection
- OpenAI API — LLM query generation

## Project structure

├── config.py          # Model, database, and scoring settings
├── pipeline.py        # Full evaluation pipeline
├── main.py            # Entry point
├── compare.py         # Compare results across runs
├── benchmarks/        # Questions and gold queries
│   ├── flat.json
│   └── nested.json
├── schemas/           # Database descriptions for the LLM
│   ├── simple.yaml
│   └── advanced.yaml
└── results/           # Saved evaluation results (auto-created)

## How it works

## Evalauation approach

### What you measure

## Examples

### Example question -> MQL