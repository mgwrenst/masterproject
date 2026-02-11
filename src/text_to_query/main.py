"""
Main benchmark runner for Norwegian text-to-MongoDB query evaluation.
"""
import json
import yaml
import re
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime
from pymongo import MongoClient
from bson import ObjectId

from config import MONGO_URI, DB_NAME
from evaluator import QueryEvaluator
from llm_utils import generate_query, load_schema


class TextToQueryBenchmark:
    """Benchmark system for evaluating Norwegian text-to-MongoDB query generation."""

    def __init__(self, data_dir: str = "../../data", results_dir: str = "../../results"):
        """
        Initialize the benchmark system.

        Args:
            data_dir: Directory containing benchmarks.json and schema.yaml
                     Default is ../../data relative to src/text_to_query
            results_dir: Directory to store benchmark results
                        Default is ../../results relative to src/text_to_query
        """
        self.data_dir = Path(__file__).parent / data_dir
        self.results_dir = Path(__file__).parent / results_dir

        # Create results directory if it doesn't exist
        self.results_dir.mkdir(parents=True, exist_ok=True)

        self.mongo_client = MongoClient(MONGO_URI)
        self.db = self.mongo_client[DB_NAME]
        self.evaluator = QueryEvaluator()

        # Load schema and benchmarks
        self.schema = load_schema()
        self.benchmarks = self._load_benchmarks()

    def _load_benchmarks(self) -> List[Dict[str, Any]]:
        """Load benchmark questions and gold standard queries from benchmarks.json."""
        benchmarks_path = self.data_dir / "benchmarks.json"
        with open(benchmarks_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _parse_mongo_command(self, command: str) -> tuple:
        """
        Parse a MongoDB command string and extract collection, operation, and parameters.

        Args:
            command: MongoDB command string (e.g., "db.collection.find({...})")

        Returns:
            Tuple of (collection_name, operation, parameters)
        """
        # Remove whitespace and newlines
        command = command.strip().replace('\n', ' ').replace('\r', '')

        # Pattern to match db.collection.operation(...)
        pattern = r'db\.(\w+)\.(\w+)\((.*)\)$'
        match = re.match(pattern, command)

        if not match:
            raise ValueError(f"Could not parse MongoDB command: {command}")

        collection_name = match.group(1)
        operation = match.group(2)
        params_str = match.group(3)

        return collection_name, operation, params_str

    def _eval_params(self, params_str: str) -> Any:
        """
        Safely evaluate parameter string to Python objects.

        Args:
            params_str: String representation of parameters

        Returns:
            Evaluated Python object
        """
        if not params_str or params_str.strip() == '':
            return None

        params_str = params_str.strip()

        try:
            # Replace single quotes with double quotes for JSON parsing
            params_str = params_str.replace("'", '"')

            # Parse multiple parameters (separated by commas at top level)
            params = []
            depth = 0
            current_param = ""
            in_quotes = False

            for i, char in enumerate(params_str):
                if char == '"' and (i == 0 or params_str[i-1] != '\\'):
                    in_quotes = not in_quotes

                if not in_quotes:
                    if char in ['{', '[']:
                        depth += 1
                    elif char in ['}', ']']:
                        depth -= 1
                    elif char == ',' and depth == 0:
                        params.append(current_param.strip())
                        current_param = ""
                        continue

                current_param += char

            if current_param.strip():
                params.append(current_param.strip())

            # Parse each parameter
            parsed_params = []
            for param in params:
                param = param.strip()
                if param.startswith('"') and param.endswith('"'):
                    # String parameter - remove quotes
                    parsed_params.append(param[1:-1])
                elif param.startswith('{') or param.startswith('['):
                    # Object or array - need to handle MongoDB operators like $ne
                    # MongoDB operators start with $, which is valid in JSON keys
                    try:
                        parsed_params.append(json.loads(param))
                    except json.JSONDecodeError as e:
                        print(f"JSON decode error for param '{param}': {e}")
                        raise
                else:
                    # Try to parse as JSON literal (number, boolean, null)
                    try:
                        parsed_params.append(json.loads(param))
                    except:
                        # If all else fails, treat as string
                        parsed_params.append(param.strip('"'))

            return parsed_params if len(parsed_params) > 1 else (parsed_params[0] if parsed_params else None)

        except Exception as e:
            print(f"Warning: Could not parse parameters '{params_str}': {e}")
            raise

    def _execute_mongo_command(self, command: str) -> List[Dict[str, Any]]:
        """
        Execute a MongoDB command string and return results.

        Args:
            command: MongoDB command string (e.g., "db.collection.find({...})")

        Returns:
            List of documents
        """
        collection_name, operation, params_str = self._parse_mongo_command(command)
        collection = self.db[collection_name]

        params = self._eval_params(params_str)

        # Execute based on operation type
        if operation == "find":
            if params is None:
                results = list(collection.find())
            elif isinstance(params, list):
                query = params[0] if len(params) > 0 else {}
                projection = params[1] if len(params) > 1 else None
                results = list(collection.find(query, projection))
            else:
                results = list(collection.find(params))

        elif operation == "aggregate":
            pipeline = params if isinstance(params, list) else [params]
            results = list(collection.aggregate(pipeline))

        elif operation == "distinct":
            if isinstance(params, list):
                field = params[0]
                query = params[1] if len(params) > 1 else {}
            else:
                field = params
                query = {}

            distinct_values = collection.distinct(field, query)
            # Convert to document format for consistent comparison
            results = [{field: value} for value in distinct_values if value is not None]

        elif operation == "count" or operation == "countDocuments":
            query = params if params else {}
            count = collection.count_documents(query)
            results = [{"count": count}]

        else:
            raise ValueError(f"Unsupported operation: {operation}")

        return results

    def _execute_query(self, collection_name: str, query: Any) -> List[Dict[str, Any]]:
        """
        Execute a MongoDB query and return results.
        Handles both string commands and dict-based queries.

        Args:
            collection_name: Name of the MongoDB collection
            query: MongoDB query (string command or dict)

        Returns:
            List of documents matching the query
        """
        # If query is a string, it's a MongoDB command
        if isinstance(query, str):
            return self._execute_mongo_command(query)

        # Check if query contains an error from the LLM
        if isinstance(query, dict) and "error" in query:
            # Return empty results for error responses
            return []

        # Otherwise, handle dict-based queries (for generated queries)
        collection = self.db[collection_name]

        # Handle distinct operation
        if query.get("operation") == "distinct":
            field = query["field"]
            filter_query = query.get("filter", {})
            distinct_values = collection.distinct(field, filter_query)
            # Convert to document format for consistent comparison
            results = [{field: value} for value in distinct_values if value is not None]
        # Handle aggregation pipeline
        elif "pipeline" in query:
            pipeline = query["pipeline"]
            results = list(collection.aggregate(pipeline))
        # Handle simple find query
        else:
            find_query = query.get("filter", query)
            projection = query.get("projection")
            sort = query.get("sort")
            limit = query.get("limit")

            cursor = collection.find(find_query, projection)
            if sort:
                cursor = cursor.sort(sort)
            if limit:
                cursor = cursor.limit(limit)

            results = list(cursor)

        return results

    def _format_results_for_display(self, results: List[Dict[str, Any]], max_display: int = 10) -> str:
        """
        Format query results for display.

        Args:
            results: List of result documents
            max_display: Maximum number of results to display

        Returns:
            Formatted string representation of results
        """
        if not results:
            return "  (No results)"

        output = []
        for i, doc in enumerate(results[:max_display], 1):
            # Convert ObjectId to string for display
            doc_copy = {}
            for key, value in doc.items():
                if isinstance(value, ObjectId):
                    doc_copy[key] = str(value)
                else:
                    doc_copy[key] = value

            output.append(f"  [{i}] {json.dumps(doc_copy, ensure_ascii=False, indent=4)}")

        if len(results) > max_display:
            output.append(f"  ... and {len(results) - max_display} more results")

        return "\n".join(output)

    def run_benchmark(self, benchmark_item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run a single benchmark test.

        Args:
            benchmark_item: Dictionary containing question, gold_query, collection, etc.

        Returns:
            Dictionary with benchmark results and evaluation metrics
        """
        question = benchmark_item["question"]
        gold_query = benchmark_item["gold_query"]
        collection = benchmark_item["collection"]

        print(f"\nProcessing question: {question}")
        print(f"Gold query: {gold_query}")

        # Generate query from natural language using existing llm_utils function
        try:
            generated_query = generate_query(question, None)
            print(f"Generated query: {generated_query}")
        except Exception as e:
            print(f"Error generating query: {e}")
            return {
                "question": question,
                "error": str(e),
                "success": False
            }

        # Execute both queries
        try:
            generated_results = self._execute_query(collection, generated_query)
            gold_results = self._execute_query(collection, gold_query)

            print(f"\nGenerated results ({len(generated_results)} documents):")
            print(self._format_results_for_display(generated_results))

            print(f"\nGold standard results ({len(gold_results)} documents):")
            print(self._format_results_for_display(gold_results))

        except Exception as e:
            print(f"Error executing queries: {e}")
            return {
                "question": question,
                "generated_query": generated_query,
                "gold_query": gold_query,
                "error": str(e),
                "success": False
            }

        # Evaluate results
        evaluation = self.evaluator.evaluate(generated_results, gold_results)

        print(f"\nEvaluation Metrics:")
        print(f"  Precision: {evaluation['precision'] * 100:.2f}%")
        print(f"  Recall: {evaluation['recall'] * 100:.2f}%")
        print(f"  F1 Score: {evaluation['f1_score'] * 100:.2f}%")

        return {
            "question": question,
            "generated_query": generated_query,
            "gold_query": gold_query,
            "evaluation": evaluation,
            "success": True
        }

    def run_all_benchmarks(self) -> Dict[str, Any]:
        """
        Run all benchmarks and aggregate results.

        Returns:
            Dictionary containing individual results and aggregate metrics
        """
        results = []
        total_precision = 0.0
        total_recall = 0.0
        total_f1 = 0.0
        successful_tests = 0

        print(f"Running {len(self.benchmarks)} benchmarks...")

        for i, benchmark in enumerate(self.benchmarks, 1):
            print(f"\n{'='*60}")
            print(f"Benchmark {i}/{len(self.benchmarks)}")
            print(f"{'='*60}")

            result = self.run_benchmark(benchmark)
            results.append(result)

            if result.get("success"):
                successful_tests += 1
                eval_metrics = result["evaluation"]
                total_precision += eval_metrics["precision"]
                total_recall += eval_metrics["recall"]
                total_f1 += eval_metrics["f1_score"]

        # Calculate averages
        avg_precision = total_precision / successful_tests if successful_tests > 0 else 0
        avg_recall = total_recall / successful_tests if successful_tests > 0 else 0
        avg_f1 = total_f1 / successful_tests if successful_tests > 0 else 0

        summary = {
            "total_benchmarks": len(self.benchmarks),
            "successful_tests": successful_tests,
            "failed_tests": len(self.benchmarks) - successful_tests,
            "average_precision": avg_precision,
            "average_recall": avg_recall,
            "average_f1_score": avg_f1,
            "individual_results": results
        }

        return summary

    def _generate_result_filename(self) -> str:
        """
        Generate a timestamped filename for the benchmark results.
        Format: benchmark_YYYYMMDD_HHMMSS_###.json where ### is sequential across all runs.

        Returns:
            Filename string with precise timestamp and global sequential number
        """
        # Get current timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Find ALL benchmark files (not just for this timestamp)
        all_files = list(self.results_dir.glob(f"benchmark_*.json"))

        # Extract the highest number from all existing files
        max_number = 0
        for f in all_files:
            match = re.search(r'_(\d+)\.json$', f.name)
            if match:
                num = int(match.group(1))
                max_number = max(max_number, num)

        # Increment for this run
        next_number = max_number + 1

        # Return filename with 3-digit zero-padded number
        return f"benchmark_{timestamp}_{next_number:03d}.json"

    def save_results(self, results: Dict[str, Any], output_file: str = None):
        """
        Save benchmark results to a JSON file in the results directory.

        Args:
            results: Dictionary containing benchmark results
            output_file: Optional custom filename (if not provided, auto-generates timestamped name)
        """
        if output_file is None:
            output_file = self._generate_result_filename()

        output_path = self.results_dir / output_file

        # Add metadata to results
        results["metadata"] = {
            "timestamp": datetime.now().isoformat(),
            "mongo_uri": MONGO_URI,
            "database": DB_NAME
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        print(f"\nResults saved to {output_path}")
        return output_path

    def close(self):
        """Close database connections."""
        self.mongo_client.close()


def main():
    """Main entry point for the benchmark."""
    # Initialize benchmark
    benchmark = TextToQueryBenchmark()

    try:
        # Run all benchmarks
        results = benchmark.run_all_benchmarks()

        # Print summary
        print("\n" + "="*60)
        print("BENCHMARK SUMMARY")
        print("="*60)
        print(f"Total benchmarks: {results['total_benchmarks']}")
        print(f"Successful tests: {results['successful_tests']}")
        print(f"Failed tests: {results['failed_tests']}")
        print(f"\nAverage Precision: {results['average_precision'] * 100:.2f}%")
        print(f"Average Recall: {results['average_recall'] * 100:.2f}%")
        print(f"Average F1 Score: {results['average_f1_score'] * 100:.2f}%")

        # Save results with auto-generated filename
        result_path = benchmark.save_results(results)

    finally:
        benchmark.close()


if __name__ == "__main__":
    main()