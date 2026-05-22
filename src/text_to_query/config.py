MODEL = "gpt-4o-mini"
TEMPERATURE = 0.0
MAX_TOKENS = 900

MONGO_URI = "mongodb://localhost:27017"
DATABASE_NAME = "groundtruth"

# Results are stored as:
# results/<benchmark_name>/<schema_name>/<timestamp>_<label>.json
RESULTS_DIR = "results"
BENCHMARKS_DIR = "benchmarks"
SCHEMAS_DIR = "schemas"
