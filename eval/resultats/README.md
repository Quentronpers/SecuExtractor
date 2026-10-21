# Evaluation reports

Every figure in the top-level README comes from a file in this folder.
Each report exists as `.json` (complete: settings, provenance, per-field
and per-datasheet counts, list of errors) and `.md` (summary). Report and
field names are in French: `miseaupoint` = development set, `test` = test
set, `sur` / `douteux` / `absent` = confident / doubtful / absent.

## Which file backs which table

| README table | Reports |
|---|---|
| Results (qwen3, prompt v1) | `2026-10-16_qwen3-14b_camera-alimentation-v1_none_{miseaupoint,test}_rejeu-regles` |
| Baseline | `2026-10-20_ligne-de-base-v1_{miseaupoint,test}` |
| Prompt iteration (v1 vs v3) | `..._v1_none_*_rejeu-regles`, `..._v3_none_*_rejeu-regles`; comparison `comparaison_..._v1_..._test_rejeu-regles__..._v3_..._test_rejeu-regles` |
| Local vs hosted (Groq) | `2026-10-19_openai-gpt-oss-120b_..._miseaupoint_rejeu-regles`, `2026-10-20_openai-gpt-oss-120b_..._test_rejeu-regles` |
| Paired comparisons | `comparaison_A__B` (A minus B, on the datasheets both share) |
| Try it (27 PDF test datasheets) | `2026-10-21_ligne-de-base-v1_test_ids27-5d06c6` |

## Kinds of report

- **`_rejeu-regles`**: replayed from the archived raw responses, without a
  model, with the final checks and ground truth. These are the figures the
  README quotes. `meta.commit_evaluation` and `meta.empreinte_corriges`
  record the code and ground truth used.
- **No suffix**: the figures as computed on the day of the run (earlier
  checks; for the 2026-10-16 runs, the former ground truth). Kept as run.
  `v2_none_miseaupoint` was never replayed: v2 was dropped first.
- **`_ids<n>-<hash>`**: a run restricted to a subset of datasheets
  (`--ids`); the name says how many and which.
- **`archives/`**: superseded reports (smoke test on 3 datasheets,
  intermediate replays, baseline before the 2026-10-20 ground-truth change).
  Quoted only as history.

`evaluate --comparer` refuses two reports scored against different ground
truths (`meta.empreinte_corriges`).

## Triage counts with and without a rule

The README gives the share of errors caught as doubtful with some rules
left out (for example "5 of 15 without the three rules shaped by test
errors"). Those counts come from the `erreurs` list of a `.json` report:
each wrong value carries its state (`etat`) and the checks that fired on it
(`regle`, separated by `; `). The denominator is the wrong values
produced (`produit` not null). An error still counts as caught without a
given set of rules if another check also fired on it. Rules shaped by test
errors: `typique_dans_couple_max`, `minimum_d_un_couple_max`,
`port_faux_marqueur`, `depasse_plafond_classe` (the README counts "three
rules": the first two form one rule on "Max. A/B W" pairs). Rules shaped by
development errors: `poe_non_maximale`, `repos_sans_max`.
