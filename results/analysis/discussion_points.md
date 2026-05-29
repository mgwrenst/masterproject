# Discussion Chapter Notes

## Database representation and query generation

The strongest structure-related F1 difference was -0.413 in the context of Complex, Technical, GPT-4.1-mini. This can be discussed in relation to schema linking, denormalization, and the cost of reasoning over embedded or referenced structures. Relevant literature areas include text-to-SQL/text-to-query schema linking, database normalization versus denormalization, and prompt grounding for structured data.

Potential citation areas: schema linking in neural semantic parsing; effects of database schema complexity on query synthesis; MongoDB document modeling and denormalization trade-offs.

## Prompt detail and schema descriptions

The strongest schema-description F1 difference was 0.335 in the context of Complex, Flat, GPT-4.1-mini. The results can support a discussion of whether additional technical metadata improves grounding or instead increases prompt load. This is a useful place to cite work on prompt specificity, context length, instruction following, and schema serialization for language models.

Potential citation areas: prompt engineering for code generation; schema serialization in text-to-SQL systems; cognitive load or irrelevant context in long prompts.

## Model capability differences

The strongest model-related F1 difference was -0.278 in the context of Complex, Flat, Technical. This can be discussed as evidence that model capability matters for query generation, especially when the task requires multi-step reasoning, operator selection, and precise syntax generation.

Potential citation areas: LLMs for code generation; LLMs for semantic parsing; benchmark studies comparing model families on structured-query generation.

## Complex aggregation pipelines

The complex benchmark produced much lower average F1 than the standard benchmark. This should be discussed as a robustness issue: aggregation pipelines are brittle because each stage depends on the correctness of earlier stages. A query can be syntactically valid while still using an incorrect grouping key, losing documents during unwinding, applying filters in the wrong order, or projecting fields that do not preserve the target answer.

Potential citation areas: compositional generalization in semantic parsing; multi-hop reasoning in LLMs; MongoDB aggregation pipeline semantics; execution-guided query generation.

## Evaluation metric limitations

Precision, recall, and F1 were computed over returned values rather than over query syntax. This is appropriate because semantically different MongoDB queries can produce equivalent result sets. However, result-equivalence scoring also has limits: equivalent outputs do not prove equivalent query semantics, and empty result sets can overstate correctness if both gold and generated queries return nothing.

Potential citation areas: execution accuracy in semantic parsing; denotation-based evaluation; limitations of exact-match metrics for query generation.

## Runtime and usability

Runtime should be interpreted as end-to-end latency from the perspective of an application user. Higher F1 may be worth additional latency in analytical settings, while interactive systems may require stricter response-time constraints. Runtime differences can also reflect generated query efficiency, not only model response latency.

Potential citation areas: human-computer interaction latency thresholds; LLM application latency; database query optimization and generated query efficiency.

## Stability across repeated runs

Because each configuration was run three times, standard deviation can be used to discuss stochastic stability. Low standard deviation strengthens confidence that the observed trends are not isolated generations. Larger deviations indicate configurations where the model is less reliable even if the mean score is acceptable.

Potential citation areas: nondeterminism in LLM outputs; reproducibility of LLM evaluations; statistical reporting for empirical software engineering.

## Threats to validity

Useful threats to validity include benchmark size, domain specificity, Norwegian-language questions, dependence on one MongoDB dataset, result-equivalence scoring, limited number of repeated runs, and the possibility that prompt templates favor one schema representation over another.

Potential citation areas: internal/external validity in empirical software engineering; dataset bias in semantic parsing; multilingual LLM performance.

## Specific difficult-question patterns

- Standard Q35 (Aggregate, Aggregate Group Count): mean F1 0.000.
- Standard Q37 (Aggregate, Aggregate Group Sum): mean F1 0.000.
- Standard Q38 (Aggregate, Aggregate Group Sum): mean F1 0.000.
- Standard Q28 (Aggregate, Quantifier Exists): mean F1 0.250.
- Standard Q52 (Aggregate, Lookup Join): mean F1 0.286.
- Standard Q14 (Find, Selection Conditions): mean F1 0.292.
- Standard Q41 (Aggregate, Aggregate Group Avg): mean F1 0.313.
- Standard Q39 (Aggregate, Aggregate Group Sum): mean F1 0.375.
- Standard Q27 (Aggregate, Quantifier Exists): mean F1 0.395.
- Standard Q22 (Aggregate, Alias Projection): mean F1 0.399.
