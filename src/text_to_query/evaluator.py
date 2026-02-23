from typing import List, Dict, Any, Tuple, Set
import json
import re


class QueryEvaluator:
    """Evaluate the accuracy of the generated MQL by comparing against gold standard"""

    def __init__(self):
        pass

    def _detect_query_type(self, query: str) -> str:
        """
        Detect if query is an aggregation or regular find.

        Args:
            query: MongoDB query string

        Returns:
            'aggregate', 'find', 'distinct', 'count', or 'unknown'
        """
        if not isinstance(query, str):
            return 'unknown'

        query = query.strip().lower()

        if '.aggregate(' in query:
            return 'aggregate'
        elif '.find(' in query:
            return 'find'
        elif '.distinct(' in query:
            return 'distinct'
        elif '.count' in query:
            return 'count'
        else:
            return 'unknown'

    def _is_aggregation_result(self, results: List[Dict[str, Any]]) -> bool:
        """
        Detect if results are from an aggregation query.
        Aggregation results typically have _id as the grouped field value.

        Args:
            results: List of result documents

        Returns:
            True if results appear to be from aggregation
        """
        if not results:
            return False

        first_doc = results[0]

        # If _id exists and is not an ObjectId-like string, it's likely aggregation
        if '_id' in first_doc:
            _id_value = first_doc['_id']
            # Check if _id is a simple value (string, number) rather than ObjectId
            if isinstance(_id_value, (str, int, float, dict)):
                # If it's a 24-char hex string, it's likely ObjectId
                if isinstance(_id_value, str) and len(_id_value) == 24:
                    try:
                        int(_id_value, 16)  # Try to parse as hex
                        return False  # It's an ObjectId
                    except ValueError:
                        return True  # Not hex, so it's a grouped value
                return True  # It's aggregation

        return False

    def _normalize_document(self, doc: Dict[str, Any], is_aggregation: bool = False) -> str:
        """
        Normalize a document for comparison.

        Args:
            doc: Document to normalize
            is_aggregation: If True, keep _id field (it's the grouped value, not MongoDB's ObjectId)

        Returns:
            JSON string representation of normalized document
        """
        if is_aggregation:
            # For aggregation results, _id is the grouped field value, so we KEEP it
            normalized = {k: v for k, v in doc.items()}
        else:
            # For find() results, _id is MongoDB's ObjectId, so we remove it
            normalized = {k: v for k, v in doc.items() if k != '_id'}

        return json.dumps(normalized, sort_keys=True, ensure_ascii=False)

    def _get_document_set(self, results: List[Dict[str, Any]], is_aggregation: bool = False) -> Set[str]:
        """
        Convert results to a set of normalized documents.

        Args:
            results: List of result documents
            is_aggregation: Whether these are aggregation results

        Returns:
            Set of normalized document strings
        """
        return {self._normalize_document(doc, is_aggregation) for doc in results}

    def calculate_precision_recall(
            self,
            generated_results: List[Dict[str, Any]],
            gold_results: List[Dict[str, Any]],
            generated_query: str = None,
            gold_query: str = None
    ) -> Tuple[float, float, float]:
        """
        Calculate precision, recall, and F1 score.

        Args:
            generated_results: Results from generated query
            gold_results: Results from gold standard query
            generated_query: Optional generated query string for type detection
            gold_query: Optional gold query string for type detection

        Returns:
            Tuple of (precision, recall, f1_score)
        """
        # Detect if this is an aggregation query
        is_aggregation = False

        # First try to detect from query strings
        if generated_query:
            is_aggregation = self._detect_query_type(generated_query) == 'aggregate'
        elif gold_query:
            is_aggregation = self._detect_query_type(gold_query) == 'aggregate'

        # If no query provided, try to detect from results
        if not is_aggregation and (generated_results or gold_results):
            is_aggregation = (
                    self._is_aggregation_result(generated_results) or
                    self._is_aggregation_result(gold_results)
            )

        # Get normalized document sets
        generated_set = self._get_document_set(generated_results, is_aggregation)
        gold_set = self._get_document_set(gold_results, is_aggregation)

        true_positives = len(generated_set.intersection(gold_set))
        false_positives = len(generated_set - gold_set)
        false_negatives = len(gold_set - generated_set)

        # Calculate precision
        if true_positives + false_positives == 0:
            precision = 0.0 if len(gold_set) > 0 else 1.0
        else:
            precision = true_positives / (true_positives + false_positives)

        # Calculate recall
        if true_positives + false_negatives == 0:
            recall = 1.0 if len(generated_set) == 0 else 0.0
        else:
            recall = true_positives / (true_positives + false_negatives)

        # Calculate F1 score
        if precision + recall == 0:
            f1_score = 0.0
        else:
            f1_score = 2 * (precision * recall) / (precision + recall)

        return precision, recall, f1_score

    def evaluate(
            self,
            generated_results: List[Dict[str, Any]],
            gold_results: List[Dict[str, Any]],
            generated_query: str = None,
            gold_query: str = None
    ) -> Dict[str, Any]:
        """
        Evaluate generated results against gold standard.

        Args:
            generated_results: Results from generated query
            gold_results: Results from gold standard query
            generated_query: Optional generated query string for analysis
            gold_query: Optional gold query string for analysis

        Returns:
            Dictionary with evaluation metrics
        """
        # Detect if aggregation
        is_aggregation = False
        if generated_query:
            is_aggregation = self._detect_query_type(generated_query) == 'aggregate'
        elif gold_query:
            is_aggregation = self._detect_query_type(gold_query) == 'aggregate'

        if not is_aggregation:
            is_aggregation = (
                    self._is_aggregation_result(generated_results) or
                    self._is_aggregation_result(gold_results)
            )

        # Calculate metrics
        precision, recall, f1_score = self.calculate_precision_recall(
            generated_results, gold_results, generated_query, gold_query
        )

        # Get sets for additional metrics
        generated_set = self._get_document_set(generated_results, is_aggregation)
        gold_set = self._get_document_set(gold_results, is_aggregation)

        true_positives = len(generated_set.intersection(gold_set))
        false_positives = len(generated_set - gold_set)
        false_negatives = len(gold_set - generated_set)

        # Calculate additional metrics
        execution_accuracy = 1.0 if generated_set == gold_set else 0.0
        journalist_score = 0.7 * recall + 0.3 * precision  # Weighted towards recall
        completeness = 1.0 if false_negatives == 0 else recall

        evaluation = {
            # Core metrics
            "precision": precision,
            "recall": recall,
            "f1_score": f1_score,

            # Journalist-focused metrics
            "execution_accuracy": execution_accuracy,
            "journalist_score": journalist_score,
            "completeness": completeness,

            # Counts
            "generated_count": len(generated_results),
            "gold_count": len(gold_results),
            "true_positives": true_positives,
            "false_positives": false_positives,
            "false_negatives": false_negatives,

            # Quality indicators
            "has_extra_data": false_positives > 0,
            "is_complete": false_negatives == 0,
            "is_exact_match": execution_accuracy == 1.0,

            # Metadata
            "detected_as_aggregation": is_aggregation
        }

        # Add query analysis if queries provided
        if generated_query and gold_query:
            evaluation["query_analysis"] = self._analyze_query_structure(
                generated_query, gold_query
            )

        return evaluation

    def _analyze_query_structure(self, generated_query: str, gold_query: str) -> Dict[str, Any]:
        """
        Analyze and compare query structures.

        Args:
            generated_query: Generated MongoDB command string
            gold_query: Gold standard MongoDB command string

        Returns:
            Dictionary with query comparison metrics
        """
        gen_parts = self._parse_query(generated_query)
        gold_parts = self._parse_query(gold_query)

        # Check for exact match
        exact_match = generated_query.strip() == gold_query.strip()

        # Compare components
        same_collection = gen_parts.get('collection') == gold_parts.get('collection')
        same_operation = gen_parts.get('operation') == gold_parts.get('operation')

        # Check if generated query is missing sort (common with aggregations)
        gen_has_sort = '$sort' in generated_query
        gold_has_sort = '$sort' in gold_query
        missing_sort = gold_has_sort and not gen_has_sort

        # Check if generated query is missing limit
        gen_has_limit = '$limit' in generated_query
        gold_has_limit = '$limit' in gold_query
        missing_limit = gold_has_limit and not gen_has_limit

        return {
            "exact_match": exact_match,
            "same_collection": same_collection,
            "same_operation": same_operation,
            "generated_operation": gen_parts.get('operation'),
            "gold_operation": gold_parts.get('operation'),
            "missing_sort": missing_sort,
            "missing_limit": missing_limit,
            "has_sort_difference": gen_has_sort != gold_has_sort,
            "has_limit_difference": gen_has_limit != gold_has_limit
        }

    def _parse_query(self, query: str) -> Dict[str, str]:
        """
        Parse a MongoDB query string into components.

        Args:
            query: MongoDB command string

        Returns:
            Dictionary with parsed components
        """
        if not isinstance(query, str):
            return {}

        # Pattern to match db.collection.operation(...)
        pattern = r'db\.(\w+)\.(\w+)\('
        match = re.search(pattern, query)

        if match:
            return {
                'collection': match.group(1),
                'operation': match.group(2)
            }
        return {}