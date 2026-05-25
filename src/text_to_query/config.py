MODEL = "gpt-4.1-mini"
MODELS = ["gpt-4.1-mini", "gpt-5-mini"]
TEMPERATURE = 0.0
MAX_TOKENS = 3000
QUERY_MAX_TIME_MS = 60000
SUCCESS_MIN_PRECISION = 0.5

MONGO_URI = "mongodb://localhost:27017"
DATABASE_NAME = "groundtruth"

# Results are stored as:
# results/<benchmark_name>/<schema_name>/<timestamp>_<label>.json
RESULTS_DIR = "results"
BENCHMARKS_DIR = "benchmarks"
SCHEMAS_DIR = "schemas"
GOLD_CACHE_DIR = "src/text_to_query/gold_cache"
