# Thesis Results Summary

## Methodological framing

The analysis is based on 48 saved evaluation runs. Each configuration was executed three times, and the values reported in the tables are arithmetic means across those repetitions. Precision, recall, and F1-score were computed over returned result values, while runtime represents the average wall-clock time per benchmark question. The standard benchmark contains the main text-to-query tasks, whereas the complex benchmark isolates aggregation-heavy pipeline questions.

## Overall performance

The strongest standard-benchmark configuration was Flat + Technical + GPT-5-mini, with mean precision 0.851, recall 0.842, and F1-score 0.840. On the complex benchmark, the strongest configuration was Flat + Technical + GPT-4.1-mini, with mean precision 1.000, recall 1.000, and F1-score 1.000. Across all configurations, the standard benchmark reached a mean F1-score of 0.754, while the complex benchmark reached 0.643. This indicates a substantial performance drop when the task requires more complex aggregation logic.

## Effect of database structure

On the standard benchmark, the flat database representation produced a mean F1-score of 0.796, compared with 0.711 for the structured representation. The flat representation also produced higher mean precision (0.803 versus 0.716) and recall (0.810 versus 0.740). In this experiment, the denormalized flat schema therefore appears easier for the models to translate into executable MongoDB queries.

## Effect of schema description

The naive schema descriptions reached a mean standard-benchmark F1-score of 0.766, while the technical schema descriptions reached 0.741. The difference is small, suggesting that more technical schema detail did not consistently improve output quality in this setup. This should be interpreted carefully because technical descriptions can help with precise field use, but may also increase prompt complexity and distract the model from the user intent.

## Model comparison

GPT-5-mini outperformed GPT-4.1-mini on the standard benchmark. GPT-4.1-mini obtained mean precision 0.710, recall 0.733, and F1-score 0.703; GPT-5-mini obtained mean precision 0.809, recall 0.818, and F1-score 0.804. The improvement is therefore visible in both retrieval completeness and result precision.

## Complex query benchmark

The complex benchmark was substantially more difficult than the standard benchmark. The mean F1-score decreased from 0.754 on standard questions to 0.643 on complex questions. This decline is consistent with the increased difficulty of generating multi-stage aggregation pipelines, where errors in joins, grouping keys, unwinding, filtering order, or projection logic can cause large deviations in the final result set.

## Runtime analysis

- Standard / GPT-4.1-mini: mean runtime 2.50 seconds per question.
- Standard / GPT-5-mini: mean runtime 8.79 seconds per question.
- Complex / GPT-4.1-mini: mean runtime 8.71 seconds per question.
- Complex / GPT-5-mini: mean runtime 25.65 seconds per question.

The runtime results should be discussed as latency rather than computational complexity. They include LLM response time, generated query execution, and scoring overhead. Differences between models therefore reflect both model latency and the interaction between generated query shape and MongoDB execution.

## Lowest-performing questions

The most difficult questions were dominated by tasks requiring cross-entity reasoning or complex aggregation. These questions often require the generated query to preserve several constraints simultaneously, such as matching people to parties, combining role counts with ownership counts, or maintaining correct grouping semantics after array unwinding.

- Standard Q35: F1 0.000, success 0.0%. Finn antall eierskapsoppføringer per år.
- Standard Q37: F1 0.000, success 0.0%. Finn totalt antall aksjer eid per person.
- Standard Q38: F1 0.000, success 0.0%. Finn totalt antall personstemmer og slengere per parti.
- Standard Q28: F1 0.250, success 25.0%. Finn personer som både har selskapsrolle og eier aksjer. Ta med navn, fødselsdato, antall roller og antall eide selskaper.
- Standard Q52: F1 0.286, success 16.7%. Finn politikere som eier aksjer. Ta med navn, fødselsdato, parti, selskap og eierandel.
- Standard Q14: F1 0.292, success 29.2%. Finn norske aksjonærer i 2023. Ta med aksjonærnavn, selskap, organisasjonsnummer, aksjeklasse, landkode, år og antall aksjer.
- Standard Q41: F1 0.313, success 29.2%. Finn gjennomsnittlig eierandel per selskap.
- Standard Q39: F1 0.375, success 37.5%. Finn totalt antall aksjer og stemmer per selskap i eierskap.
