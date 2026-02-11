from typing import List, Dict, Any, Tuple, Set
import json

class QueryEvaluator:
    """Evaluate the accuracy of the generated mql by comparing against gold standard"""

    def __init__(self):
        pass

    def _normalize_document(self, doc: Dict[str, Any]) -> str:
        normalized = {k: v for k, v in doc.items() if k != '_id'}
        return json.dumps(normalized, sort_keys=True, ensure_ascii=False)

    def _get_document_set(self, results: List[Dict[str, Any]]) -> Set[str]:
        return {self._normalize_document(doc) for doc in results}

    def calculate_precision_recall(self, generated_results: List[Dict[str, Any]], gold_results: List[Dict[str, Any]]) -> Tuple[float, float, float]:
        generated_set = self._get_document_set(generated_results)
        gold_set = self._get_document_set(gold_results)
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

    def evaluate(self, generated_results: List[Dict[str, Any]], gold_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        precision, recall, f1_score = self.calculate_precision_recall(generated_results, gold_results)
        return {
            "precision": precision,
            "recall": recall,
            "f1_score": f1_score,
            "generated_count": len(generated_results),
            "gold_count": len(gold_results),
            "true_positives": len(
                self._get_document_set(generated_results).intersection(
                    self._get_document_set(gold_results)
                )
            )
        }