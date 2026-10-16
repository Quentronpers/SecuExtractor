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

## Results

First real run, 2026-10-16: `qwen3:14b` on Ollama (digest `bdbd181c…`),
prompt `camera-alimentation-v1`, temperature 0, no reasoning, one run,
16 GB GPU. Figures are copied from `eval/resultats/`; brackets are 95 %
bootstrap intervals over datasheets.

| | Development (15 datasheets, 165 cells) | Test (35 datasheets, 385 cells) |
|---|---|---|
| Precision | 90.4 % [82.9 ; 97.1] | 91.5 % [85.9 ; 96.2] |
| Precision of confident values | 95.8 % [90.7 ; 100.0] | 95.6 % [92.6 ; 98.2] |
| Recall | 85.5 % [77.1 ; 93.2] | 89.1 % [83.2 ; 94.2] |
| Cell accuracy | 89.7 % [84.2 ; 95.2] | 90.4 % [85.7 ; 94.5] |
| Invention | 1.8 % [0.0 ; 5.9] | 6.7 % [1.0 ; 13.9] |
| Underestimation (peak / PoE power) | 3.4 % [0.0 ; 10.3] | 4.6 % [0.0 ; 10.1] |
| Errors caught as doubtful | 60.0 % [33.3 ; 100.0] | 54.5 % [25.0 ; 74.2] |
| Technical failures | 0.0 % | 0.0 % |
| Mean time per datasheet | 10.7 s | 8.3 s |

Baseline (regular expressions on the same selected text): precision
69.0 % on the development set and 82.7 % [74.3 ; 90.7] on the test set;
precision of confident values 77.0 % and 86.8 %; recall 72.7 % and
77.1 %; invention 20.0 % and 11.8 %. The test-set datasheets are easier
for the baseline than the development ones: the gap the model has to
justify is about 9 points of precision, not 20.

Against the targets fixed beforehand: peak-power precision on the test set
is 91.2 % (target 90 %, met); invention is 6.7 % (target 2 %, missed);
errors caught as doubtful are 54.5 % (target 80 %, missed). The test set
confirms the development set, so there is no sign of overfitting to it.

**Plausibility rule added afterwards** (no model involved, replayed on the
same raw responses): when the datasheet cites several power inputs and
the extracted peak power is below the highest consumption it cites, the
value becomes doubtful. A wattage counts as a cited consumption when the
text before it on the line carries a consumption cue (max, typical,
approx., consumption) and no rating cue (midspan, injector, supply, PoE
class or standard, proprietary PoE, switch, output). On the development
set, errors caught as doubtful rise from 60.0 % to 80.0 % (8 of 10) and
precision of confident values from 95.8 % to 97.8 %; it catches hanwha-07
and ms-01, for one false alarm on a multi-reference sheet (ms-03, whose
neighbouring variant draws more). On the test set the figures are 54.5 %
to 63.6 % (14 of 22) and 95.6 % to 96.4 %, but they are biased upwards:
parts of the rule (the "Ethernet" capacity exclusion, the reading of a
second value on the same line) were adjusted on test datasheets. "Errors
caught as doubtful" counts wrong values produced; missed fields (absent
instead of a value) are not in it.

### Prompt iteration: tried, not kept

Two revised prompts were written from the error analysis of the first
run. **That analysis covered both sets**: nine test datasheets (axis-01,
axis-04, bosch-02, bosch-03, dahua-04, hik-02, hik-03, hik-06, ipro-04)
shaped the new wording. v2 and v3 were then judged on the development set,
v3 was measured once on the test set, and the choice between versions was
made after seeing that measurement. Same model and settings; v1 is
replayed with the same checks, plausibility rule included. Exact prompt
texts are in `eval/prompts/`.

| | v1 dev | v3 dev | v1 test | v3 test |
|---|---|---|---|---|
| Precision | 90.4 % | 97.1 % | 91.5 % | 91.8 % [87.0 ; 95.6] |
| Precision of confident values | 97.8 % | 100.0 % | 96.4 % | 95.1 % [91.2 ; 98.4] |
| Recall | 85.5 % | 92.7 % | 89.1 % | 88.0 % [81.7 ; 93.3] |
| Invention | 1.8 % | 0.0 % | 6.7 % | 2.5 % [0.0 ; 5.6] |
| Underestimation | 3.4 % | 3.4 % | 4.6 % | 3.2 % [0.0 ; 7.9] |
| Errors caught as doubtful | 80.0 % (8/10) | 100.0 % (3/3) | 63.6 % (14/22) | 47.6 % (10/21) |
| Wrong values marked confident | 2 | 0 | 8 | 11 |

Split of the test errors (all states, of which confident in brackets):

| Test datasheets | v1 | v3 |
|---|---|---|
| the 9 that shaped the prompt | 23 (8) | 12 (5) |
| the 26 others | 14 (0) | 23 (6) |

v3 fixes the cases it was written from and gets worse on the datasheets
that played no part in it: six wrong values come out confident where v1
had none. Peak-power precision on the test set falls from 91.2 % to
88.2 % (target 90 %). Some new errors come straight from the added
wording: "compare all PoE modes, High PoE included" made the model take a
90 W High PoE capacity for a consumption (axis-09); quoting "the line that
lists the power inputs" led it to declare the DC input false on a sheet
that lists one input per line (axis-05); dahua-03's DC input is also
declared false, with no clear cause; ms-02 values from a
neighbouring column now carry a well-formed quote, so the citation check
no longer flags them. Three versions judged on 15 datasheets is
overfitting, and a paired comparison of v1 and v3 has not been computed.
**v1 stays the prompt**; v2 and v3 are reported as an attempt that did
not generalise. A further prompt change would need fresh datasheets to be
judged, since the test set is no longer blind to it.

### Typical errors

The dangerous ones are wrong values marked confident. The main cause is
**the maximum taken from one power source instead of the maximum over all of
them**, which underestimates a calculation field:

- hanwha-07, peak power 60 W instead of 92 W (the 24 V AC figure was missed);
- ipro-04, PoE power 25 W instead of 50 W (60 W PoE injector);
- axis-04 (23 instead of 24 W, DC above PoE) and bosch-02 (10.59 instead
  of 10.76 W, AC above PoE).

The others: a 24 V AC figure filed under DC or PoE (hik-06, bosch-03); a
misread table (an auxiliary 12 V DC output taken for an input, a 4 A supply
rating taken for a consumption, the wrong "Basic" value, the column of a
neighbouring reference on a multi-reference sheet); and a typical power
filled with the maximum when the datasheet gives no typical value (hik-02,
hik-03).

## Limitations, stated up front

- **One run, one model.** Each figure comes from a single run at
  temperature 0 with `qwen3:14b` (prompt v1; v2 and v3 tried): no Groq
  comparison, no reasoning mode yet. Repeat runs would only show GPU non-determinism.
- **Web pages do not reproduce exactly.** The SHA-256 of a re-downloaded
  HTML page changes between downloads (tokens, scripts): 7 of the 10 pages
  (dahua-01 to 04, hanwha-01, 02, 06) differ from the files used, though
  every ground-truth quote is still present. PDFs reproduce: 43 of 50
  files matched on re-download, the 40 PDFs and 3 of the 10 pages. A third party therefore cannot retrieve
  those 7 pages identically.
- **The test set is not fully clean.** The annotation guide, the prompt and
  some rule bounds were written while annotating all 50 datasheets, and two
  test datasheets (dahua-03, dahua-04) are quoted as examples in the prompt.
  The error analysis of the first run also covered test datasheets, and it
  shaped the prompt revisions (see "Prompt iteration"); v1 predates it.
- **Small sample.** 15 development and 35 test datasheets: intervals
  around ±10 points, and wider on rare cases.
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

## Try it

Two paths: one without a GPU (a few minutes), one with a local model.
Both need Linux or macOS, Python 3.12 and git. Commands run from the
repository root.

**Install** (one or two minutes; the dependencies include Playwright and
Streamlit, used elsewhere in the pipeline):

```bash
git clone https://github.com/Quentronpers/SecuExtractor.git && cd SecuExtractor
python3.12 -m venv .venv && .venv/bin/pip install -e .
export SECURSCOPE_CONTACT="you@example.com"   # contact sent in the User-Agent
```

**Without a GPU: download the datasheets and score the baseline.**

```bash
.venv/bin/catalog recuperer --archiver        # a few minutes: 2–3 s between requests, robots.txt honoured
IDS=$(awk -F, 'NR>1 && $NF=="test" && $5=="pdf" {print $1}' eval/notices.csv | paste -sd,)
.venv/bin/catalog evaluate --ligne-de-base --jeu test --ids "$IDS"   # ~15 s
```

`recuperer` re-downloads the 50 datasheets and checks each SHA-256
against `eval/notices.csv`. Expect 43 `recupere` and 7 `modifie`: the 7
web pages have changed since they were annotated (see Limitations) and
are not archived. Hence the `IDS` line, which keeps the PDF datasheets
only (27 of the 35 test datasheets; it also leaves out 3 pages that did
reproduce, to keep the filter simple). Without it, the command stops on
the first missing page. On those 27, the baseline gives a precision of
81.1 % [70.5 ; 90.5] and a recall of 79.5 %
(`eval/resultats/2026-10-16_ligne-de-base-v1_test_ids27-5d06c6.json`); a
run with `--ids` is named after its subset, so it never overwrites the
full report. These figures cover fewer datasheets than the
Results table, so they differ from it.

**With a local model** (an NVIDIA GPU with 16 GB, measured on an RTX 5070
Ti; about 3 minutes for the development set and 5 for the test set):

```bash
# Ollama installed (ollama.com), with a 16k context:
#   OLLAMA_CONTEXT_LENGTH=16384 ollama serve
ollama pull qwen3:14b                         # 9.3 GB
.venv/bin/catalog extract --jeu test --ids "$IDS"
.venv/bin/catalog evaluate --run data/extractions/resultats/<folder printed by extract>
```

Ollama on `127.0.0.1:11434` and `qwen3:14b` are the defaults; set
`LLM_BASE_URL` or `LLM_MODEL` to use another server or model. If Ollama is
unreachable, the model is missing or a datasheet is not on disk, the
command says what to run. GPU results are not bit-for-bit identical
between machines, and "Try it" runs on 27 of the 35 test datasheets, so
expect figures close to the v1 test column, not equal.

## Reproducing

The code, comments and internal docs are in French; this README is the
English entry point. Tests and checks run in a container (or in a local virtual environment, see below).

```bash
docker compose up -d dev
docker exec dev_catalog sh -c "cd /app && ruff format --check catalog tests \
  && ruff check catalog tests && mypy && pytest"
docker exec dev_catalog sh -c "cd /app && python -m catalog.evaluation.reference"  # validate ground truth
```

No test calls the network or a model. Fixtures are hand-built files; the
tests also read the ground-truth quotes.

Running an extraction needs a GPU host with Ollama and the datasheets on
disk. **A third party cannot reproduce the published scores exactly**:
`catalog recuperer` re-downloads the 50 datasheets from `eval/notices.csv`
and checks each SHA-256, but 7 HTML pages no longer match (see
Limitations), so "Try it" runs on the PDF datasheets only. On the author's
machine (Linux, no Docker,
a local virtual environment):

```bash
python3.12 -m venv .venv && .venv/bin/pip install -e . ruff mypy pytest
sudo systemctl edit ollama      # Environment="OLLAMA_CONTEXT_LENGTH=16384", then restart
ollama pull qwen3:14b
.venv/bin/catalog extract --jeu miseaupoint      # local Ollama and qwen3:14b by default
.venv/bin/catalog evaluate --run data/extractions/resultats/<folder>
```

`--jeu miseaupoint` is the development split (`test` for the test split);
`--fournisseur groq --reflexion low` with `LLM_API_KEY` and `LLM_MODEL`
set runs the comparison (Groq's reasoning models reject `none`, so the
command refuses it); `LLM_BASE_URL` and `LLM_MODEL` point to another
server or model. Raw
responses go to `data/extractions/` (not versioned: they contain datasheet
text). `evaluate` replays checks and metrics from them without a model, and
`catalog evaluate --ligne-de-base --jeu test` scores the regular-expression
baseline.

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
