# Result analysis

Generated from 48 result files.

## Best aggregate configuration

- complex / flat / advanced / gpt-4.1-mini: success 100.0%, F1 1.000 across 3 run(s).

## Recommended thesis tables

- `latex/main_config_comparison.tex`: compact overview of the ordinary benchmark.
- `latex/complex_config_comparison.tex`: compact overview of the complex pipeline benchmark.
- `latex/model_comparison.tex`: model-to-model deltas while holding structure and schema description fixed.
- `latex/schema_description_effect.tex`: naive versus advanced schema description deltas.
- `latex/structure_effect.tex`: flat versus structured database deltas.
- `latex/operation_performance.tex`: broad query operation types ranked by average F1.
- `latex/query_type_performance.tex`: detailed query categories ranked by average F1.
- `latex/difficult_questions.tex`: questions with the lowest average F1 across configurations.

The LaTeX fragments use `booktabs`, so add `\usepackage{booktabs}` in Overleaf if it is not already included.

## Notes for interpretation

- Mean values aggregate repeated runs of the same benchmark, structure, schema description, and model.
- Delta tables report the second condition minus the first condition, so positive values mean the second condition performed better.
- The CSV files contain fuller versions of the same data and are better suited for appendix tables or manual checks.

## Quick findings

- Model effect: largest F1 delta is -0.278 for complex, flat, advanced.
- Schema-description effect: largest F1 delta is 0.335 for complex, flat, gpt-4.1-mini.
- Structure effect: largest F1 delta is -0.413 for complex, advanced, gpt-4.1-mini.

## Most difficult questions

- Q101 (complex, complex_pipeline_stress): F1 0.212, success 16.7% - Finn partier med politikere som har selskapsroller. Identifiser politikere med navn og fødselsdato. Ta med parti, antall unike politikere...
- Q105 (complex, complex_pipeline_stress): F1 0.220, success 16.7% - Finn partier der politikere har minst én selskapsrolle eller minst ett personlig eierskap. Identifiser politikere med navn og fødselsdato...
- Q102 (complex, complex_pipeline_stress): F1 0.679, success 58.3% - Finn selskaper som både har eierskapsoppføringer i 2023 og aksjeeierbokoppføringer i 2023. Ta med navn, organisasjonsnummer, antall eiers...
- Q104 (complex, complex_pipeline_stress): F1 0.875, success 87.5% - Finn de 20 selskapene med flest samlede rolleoppføringer og eierskapsoppføringer. Ta med navn, organisasjonsnummer, antall roller, antall...
- Q103 (complex, complex_pipeline_stress): F1 0.917, success 91.7% - Finn politikere som både eier aksjer i et selskap og har en rolle i samme selskap. Identifiser politikere med navn og fødselsdato. Ta med...
- Q35 (main, aggregate_group_count): F1 0.000, success 0.0% - Finn antall eierskapsoppføringer per år.
- Q37 (main, aggregate_group_sum): F1 0.000, success 0.0% - Finn totalt antall aksjer eid per person.
- Q38 (main, aggregate_group_sum): F1 0.000, success 0.0% - Finn totalt antall personstemmer og slengere per parti.
- Q28 (main, quantifier_exists): F1 0.250, success 25.0% - Finn personer som både har selskapsrolle og eier aksjer. Ta med navn, fødselsdato, antall roller og antall eide selskaper.
- Q52 (main, lookup_join): F1 0.286, success 16.7% - Finn politikere som eier aksjer. Ta med navn, fødselsdato, parti, selskap og eierandel.
