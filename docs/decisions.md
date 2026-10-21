# Design decisions (English summary)

The full log is `docs/chantiers/plan-eval-alimentation.md`, in French: the
plan as validated on 2026-10-15, then one journal section per work package
(L1 to L6), with the reviews and the figures of each step. The decisions
that shape the results:

| Decision | Why | Where |
|---|---|---|
| Each field carries its own state (confident, doubtful, absent) and its source quote | A value nobody re-read is usable if it says so; review time goes to doubtful fields first | `catalog/extraction/etats.py`, `citations.py` |
| SecurScope's data model fixes the 11 fields and their units | The client decides what is worth extracting | `catalog/extraction/cibles/` |
| One narrow strict JSON schema per block, quote before value | Reliability drops with schema width; the model commits to a quote first | `catalog/extraction/prompts.py` |
| Local model first (`qwen3:14b`, 16 GB GPU), one hosted model for comparison (Groq) | Zero cost per call, datasheets stay on the machine; the hosted model gives a ceiling | plan § 2 |
| Every raw response archived under a hash key, metrics replayed without a model | GPU time and quota are scarce, checks change often | `catalog/extraction/brut.py`, `catalog/evaluation/rejeu.py` |
| Metrics and targets fixed before the first run | They cannot be picked after seeing results | plan § 4, README "Planned metrics" |
| Ground truth annotated by Claude, uncertain fields and a random sample reviewed by me | Changed on 2026-10-16 from annotation by hand; an LLM annotator may share an extractor's reading errors, so the limit is published | `eval/GUIDE.md`, README "Limitations" |
| A check that rejects a correct ground-truth value is wrong | Rules are tested against all 50 annotated datasheets, with one documented exception | `tests/test_controles_corrige.py` |
| Prompts v2 and v3 measured and dropped; v1 kept | v3 fixed the datasheets it was written from and got worse on the others | `eval/prompts/`, README "Prompt iteration" |
| Triage published without the rules shaped by test errors | Those rules inflate the test figure | README "Local vs hosted" |
| Two-mode PoE: class and wattage of the worst case (ground truth changed 2026-10-20) | Pairing the low mode's class with the high mode's wattage was incoherent | `eval/GUIDE.md`, plan L5 |
