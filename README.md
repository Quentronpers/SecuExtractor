# SecuExtractor — how often does a local LLM get CCTV power specs wrong?

A measured pipeline that extracts IP-camera power data from manufacturer
datasheets with a local LLM. Every value carries its source quote, is
checked by deterministic code, and is scored against a 50-datasheet ground
truth.

## The problem

A security integrator sizing a CCTV installation needs, for every camera,
its peak power draw, its PoE class and standard, and its DC input range.
Those numbers decide which PoE switch and which power supply go on site.
They live in thousands of PDF and HTML datasheets, each with its own layout
and traps: typical versus maximum consumption, heaters and IR that only draw
in winter, proprietary "Hi-PoE", 24 V AC inputs, one datasheet covering six
references.

The client is the author's own product: **SecurScope**, a security-design
tool (private) that places equipment on plans and checks PoE budgets and
power compatibility. It needs a catalogue of up to **50,000
electronic-security references**: cameras, recorders, switches, intrusion
panels, access control, power supplies. At that volume, nobody can re-read every value by
hand, and a per-call API bill grows with every datasheet. The extraction
has to run unattended, cheaply, and say by itself which values a human
should check first. This repository is the first slice: one family (IP
cameras), one block of fields (power), measured before scaling out.

An LLM can read datasheets at scale. But a plausible wrong value is worse
than no value: underestimating a camera's peak draw undersizes the switch,
and the error only shows on a real site. So the question is not "can an LLM
extract this?" but **"how often is it wrong, and does the system know when
it is?"**

## The approach

**Every value enters the catalogue; none lies about its reliability.**
Each field, not each product, carries its own state:

| State | Meaning |
|---|---|
| confident | Value found, quote verified in the document, plausibility rules passed. |
| doubtful | Value found, but the quote does not check out, a rule failed, the type is wrong, or the model flagged a doubt. Goes first in the human review queue. |
| absent | Not in the document. Never inferred. |

(Stored as `sur` / `douteux` / `absent` in the code.) In case of
hesitation, doubtful: a false alarm costs a minute of review, a false
"confident" costs a wrong switch on a real job site.

How a datasheet becomes eleven fields:

```
datasheet (PDF or HTML)
  │
  ├─ read ──────────── text + tables per page (pdfplumber) or per section (HTML)
  ├─ select ────────── pages about power (at most 4), whole document if short
  ├─ extract ───────── one narrow strict JSON schema per block (11 fields),
  │                    each field = { quote, page, value, doubt }
  ├─ check citation ── is the quote on that page? is the value in the quote,
  │                    as a delimited number with its unit?          (no LLM)
  ├─ check rules ───── PoE class vs standard, wattage under the class ceiling,
  │                    DC voltage near 12/24/36/48 V, V × I vs W …   (no LLM)
  └─ state ─────────── confident / doubtful / absent, with the failed rule
```

Design choices worth noting:

- **Local model first, one client.** `qwen3:14b` on Ollama, one 16 GB GPU:
  no cost per call, no document leaves the machine — what an industrial
  client asks for. A larger open model on Groq gives the ceiling for
  comparison (that run does send datasheet text to Groq). Both go through
  one OpenAI-compatible client with a strict JSON schema, validated again
  with Pydantic.
- **The citation check is code, not a model.** "7.7" does not match
  "17.7 W"; decimals, ranges and "± 25 %" tolerances are parsed; for peak
  power, a higher value in the same quote marks the field doubtful.
- **The quote comes before the value** in the schema, so that where
  decoding is grammar-constrained (Ollama) the model copies the source
  before concluding. Whether it helps is not measured yet.
- **Every raw response is archived** under a hash of everything that shapes
  it: model name and Ollama digest, prompt version, exact messages, schema,
  sampling parameters, context length, run index. Checks and metrics replay
  from the archive without a GPU.
- **Silent truncation is a failure, never an `absent`.** Ollama's `/v1`
  endpoint cuts long prompts without an error. The runner reads the real
  context from `/api/ps`, refuses prompts estimated too long, and fails any
  response whose `finish_reason` or token counts show it hit the context.
- **The target fields come from SecurScope's data model**, with its keys,
  units and source commit
  (`catalog/extraction/cibles/camera_alimentation.json`): the catalogue is
  imported as-is, through a versioned JSON file and nothing else.

## The evaluation set

| | |
|---|---|
| Datasheets | 50 public datasheets, 10 manufacturers (Axis, Hanwha, Hikvision, Vivotek, Bosch, Dahua, i-PRO, Mobotix, Milesight, Uniview) |
| Formats | 40 PDF, 10 HTML product pages |
| Types | domes, bullets, PTZ |
| Split | 15 development (used to tune the prompt), 35 test (the published scores); stratified random draw, fixed seed |
| Fields | 11 per datasheet: PoE and DC input present, typical and peak power, PoE class / standard / worst-case wattage, DC voltage range, standby and peak current |
| Traps covered | multi-reference sheets, heaters, PoE-only, current given, 24 V AC or DC, 24 V AC only, VA instead of W, proprietary PoE, > 90 W PTZ |

The datasheets are **not redistributed**. `eval/notices.csv` lists each URL
and the SHA-256 of the exact file used. The ground truth
(`eval/reference/<id>.json`) gives, for each field, the value, the expected
state, the page (or HTML section) and the exact quote. Ambiguous cases are
settled in `eval/GUIDE.md` (e.g. "12 V DC ± 25 %" → 9 to 15 V; never the
48 V switch-side PoE voltage as a DC input; a current is never derived from
watts).

### Planned metrics

Planned before any run, so they cannot be picked after seeing results:

- **Scoring rule**: exact match after unit and decimal normalisation; a
  1 % gap is reported separately, never counted right. Any non-absent value
  counts as produced.
- **Per field**: precision, precision of confident values (what the
  application consumes without warning), recall, **invention rate**
  (fields absent from the datasheet but filled), **underestimation rate** of
  peak and PoE power (the error that undersizes a switch), citation
  failures, and **triage rate**: the share of errors that landed in
  doubtful, i.e. that the system caught.
- **Overall**: cell accuracy, technical failures (truncation, invalid JSON,
  HTTP), seconds and tokens per datasheet, local vs Groq.
- **Page-selection recall**: is the page of each ground-truth value sent to
  the model? It bounds everything else.
- **Uncertainty**: 95 % bootstrap intervals resampled over datasheets;
  paired bootstrap between models; per-field counts published.
- **Baseline**: regular expressions on the same selected text, scored the
  same way, to show what the model actually adds.
- **Targets** for the best local model: precision ≥ 90 % on peak power,
  invention ≤ 2 %, triage ≥ 80 % of errors.

## Limitations, stated up front

- **No real extraction has run yet.** The schema has only been tested
  against fakes; the first run on a real server comes next.
- **The test set is not fully clean.** The annotation guide, the prompt and
  some rule bounds were written while annotating all 50 datasheets, and two
  test datasheets (dahua-03, dahua-04) are quoted as examples in the prompt.
  The test set is held out from prompt iteration only. Results on those two
  will be reported separately.
- **Small sample.** 35 test datasheets: intervals around ±10 points.
  Currents and PoE-less cameras rest on few cases.
- **The ground truth was annotated by Claude, then reviewed by a human.**
  The 20 fields Claude marked uncertain were decided by the author; 5
  datasheets drawn at random (55 cells) were fully re-checked with no
  discrepancy. That does not prove an error-free ground truth, and an LLM
  annotator may share reading errors with an LLM extractor. Every
  disagreement between a model and the ground truth will be re-read by hand,
  and ground-truth errors counted. None of the evaluated models is Claude.
- **Citation check blind spots.** In "6.4 W (12 V DC); 7.7 W (PoE)", both
  numbers are in the quote, so swapping them passes. A port declared absent
  (`false`) is not checked against the quote.
- **Repeat runs measure little.** At temperature 0 the seed has no effect;
  repeated runs only show GPU non-determinism.
- **Groq exposes no model digest**: a model changed under the same name is
  not detected.
- **Coverage gaps.** Manufacturers that publish web pages only (Ajax, ABUS)
  returned 403 and were excluded, so "HTML only" is not tested; no datasheet
  gives a PoE class without its standard. Sites behind anti-bot challenges
  were replaced, never bypassed; `robots.txt` is honoured (RFC 9309).
- **One family, one block.** Nothing here yet says how the method carries
  over to intrusion panels or access control.

## Where this is going

Not built yet; each step starts only once the previous one is measured.

1. **More fields, more families**: the same method, block by block
   (identification, environment, physical), then recorders, switches,
   intrusion, access control, power supplies.
2. **Acquisition at scale**: start from a list of manufacturers, find
   product pages and datasheets (sitemaps first), polite crawling, and a
   log of every failure so the manual work is targeted. Manufacturer data
   feeds where they exist.
3. **Review queue**: a local app that serves doubtful values first, and
   values used in real SecurScope projects before those nobody uses;
   validating one takes seconds and makes it "verified" for every user.
4. **Export**: a versioned JSON catalogue that SecurScope imports, each
   field carrying its source quote and its reliability level, so a
   calculation built on unverified data says so.

## Reproducing

The code, comments and internal docs are in French; this README is the
English entry point. Everything runs in a container.

```bash
docker compose up -d dev
docker exec dev_catalog sh -c "cd /app && ruff format --check catalog tests \
  && ruff check catalog tests && mypy && pytest"
docker exec dev_catalog sh -c "cd /app && python -m catalog.evaluation.reference"  # validate ground truth
```

No test calls the network or a model. Fixtures are hand-built files; the
tests also read the ground-truth quotes.

Running an extraction needs a GPU host with Ollama and the datasheets on
disk. **Today a third party cannot do it from the repository alone**: the
runner finds each datasheet through `data/sources/manifeste.json`, which is
not versioned, and a re-downloaded file may no longer match its SHA-256. A
download-and-verify script is planned. On the author's machine (Linux):

```bash
OLLAMA_CONTEXT_LENGTH=16384 OLLAMA_HOST=0.0.0.0 ollama serve   # exposes Ollama on the LAN
ollama pull qwen3:14b
docker exec -e LLM_BASE_URL=http://172.17.0.1:11434/v1 -e LLM_MODEL=qwen3:14b \
  dev_catalog sh -c "cd /app && python -m catalog.cli extract --jeu miseaupoint"
```

`--jeu miseaupoint` is the development split (`test` for the test split);
`--fournisseur groq` with `LLM_API_KEY` set runs the comparison. Raw
responses go to `data/extractions/` (not versioned: they contain datasheet
text). Replaying checks and metrics from them (`evaluate`) comes with the
metrics.

## Repository layout

```
catalog/   readers, extraction, citation and plausibility checks, evaluation
eval/      notices.csv, GUIDE.md, reference/ (ground truth)
docs/      pipeline.md, chantiers/ (design decisions, in French)
```

`tests/test_architecture.py` enforces module boundaries and size limits.

## How it was built

The author is both the builder and the client: the scope, the field
definitions, the domain rules and the evaluation protocol come from
SecurScope's needs. Most of the code was written with Claude Code, under
the author's review; design decisions are logged in
`docs/chantiers/plan-eval-alimentation.md`. Claude annotated the ground
truth and the author reviewed it. Claude is not one of the evaluated models.
