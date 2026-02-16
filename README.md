# pydanticforge

[![PyPI](https://img.shields.io/pypi/v/pydanticforge.svg)](https://pypi.org/project/pydanticforge/)
[![Python](https://img.shields.io/pypi/pyversions/pydanticforge.svg)](https://pypi.org/project/pydanticforge/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Infer robust Pydantic v2 models from messy, evolving JSON streams.**

Pydanticforge helps you go from raw JSON (APIs, logs, LLM output) to typed Python models without hand-writing schemas. It infers types from real samples, merges them in an order-independent way, and can detect when new data no longer fits the inferred schema (drift).

---

## Table of contents

- [Why pydanticforge?](#why-pydanticforge)
- [Requirements](#requirements)
- [Dependency breakdown](#dependency-breakdown)
- [Installation](#installation)
- [Quick start](#quick-start)
- [How it works (for new Python developers)](#how-it-works-for-new-python-developers)
- [Implementation details by command](#implementation-details-by-command)
- [Commands in detail](#commands-in-detail)
- [Use cases and examples](#use-cases-and-examples)
- [Programmatic API](#programmatic-api)
- [Public API method reference](#public-api-method-reference)
- [Input and output formats](#input-and-output-formats)
- [Open source standards](#open-source-standards)
- [Development](#development)
- [License](#license)

---

## Why pydanticforge?

- **APIs and scrapers** often return JSON where some fields appear only sometimes, or types change (e.g. `"id"` as number in one response and string in another).
- **LLM output** and user-submitted JSON are inconsistent; manually keeping Pydantic models in sync is tedious and error-prone.
- **Logs and event streams** evolve over time; new fields get added and old code breaks if the schema is not updated.

Pydanticforge:

1. **Infers** a single schema from many JSON samples (streaming or from files).
2. **Generates** Pydantic v2 `BaseModel` classes you can use in your app.
3. **Monitors** directories of JSON files and reports when data no longer matches the inferred schema (drift).
4. **Diffs** two generated model files and classifies changes as breaking vs non-breaking.

You get type-safe models that stay in sync with real data instead of hand-maintained schemas that drift out of date.

---

## Requirements

- **Python 3.10+**
- **Package manager:** `pip` (latest recommended)
- **Dependencies:** see the full dependency matrix below

## Dependency breakdown

This table is the source-of-truth for package dependencies and their purpose.

| Dependency | Type | Why it is used | Where used |
|---|---|---|---|
| `pydantic` | Runtime | Generated models target Pydantic v2 APIs (`BaseModel`, `RootModel`, `ConfigDict`). | Generated model code (`modelgen.emit`) |
| `orjson` | Runtime (optional fast path) | Faster JSON decode for file and stream ingestion, with stdlib `json` fallback. | `src/pydanticforge/io/files.py`, `src/pydanticforge/io/stream.py` |
| `typer` | Runtime compatibility | Kept for CLI roadmap compatibility and potential UX migration. | Packaging metadata (`pyproject.toml`) |
| `rich` | Runtime compatibility | Kept for richer terminal output roadmap. | Packaging metadata (`pyproject.toml`) |
| `watchfiles` | Runtime compatibility | Kept for continuous watch-mode roadmap (`monitor` Phase 3). | Packaging metadata (`pyproject.toml`) |

Dev-only tools (`build`, `twine`, `ruff`, `mypy`, `pytest`, `pytest-cov`, `hypothesis`, `pip-audit`, `pre-commit`) are defined in `pyproject.toml` under `[project.optional-dependencies].dev`.

Dependency policy:

- New dependency additions must include README and `pyproject.toml` updates in the same PR.
- Unused dependencies should be removed or moved to optional extras.
- Security-impacting dependency changes must run `pip-audit` before release.

---

## Installation

From PyPI:

```bash
pip install pydanticforge
```

From source (e.g. for development):

```bash
git clone https://github.com/adwantg/pydanticforge.git
cd pydanticforge
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

The CLI is available as `pydanticforge`:

```bash
pydanticforge --help
```

---

## Quick start

**1. Generate Pydantic models from sample JSON (stdin)**

```bash
echo '{"id": 1}
{"id": 2, "name": "alice"}' | pydanticforge generate --output models.py
```

This produces `models.py` with a root model whose fields are inferred from both objects: `id` (required) and `name` (optional, because it appeared in only one sample).

**2. Save inferred schema state for later**

```bash
cat samples.ndjson | pydanticforge generate --output models.py --save-state .pydanticforge/state.json
```

**3. Watch a directory for new JSON and check for drift**

```bash
pydanticforge monitor ./logs --state .pydanticforge/state.json
```

**4. Compare two model versions (e.g. before/after a change)**

```bash
pydanticforge diff models_v1.py models_v2.py
```

---

## How it works (for new Python developers)

### Inference and the “lattice join”

Pydanticforge does **schema inference**: it looks at many JSON values and builds a single type that fits all of them.

- Each JSON value is turned into an internal **type node** (e.g. object with fields, array of items, string, int, float, etc.).
- When you feed multiple samples, it **joins** their types with rules that are **order-independent** (associative and commutative), so you get the same result no matter the order of samples.

Examples of join rules:

- Same type → same type (e.g. `int` + `int` → `int`).
- Different scalars → union (e.g. `int` and `str` → `int | str`).
- `int` and `float` → by default merged to `float` (or `int | float` with `--strict-numbers`).
- Two objects → one object with **merged fields**; a field present in only some samples becomes **optional** in the generated model.
- Two arrays → array of the join of their item types.
- `null` and another type → `type | None`.

So: **required** = field appeared in every sample; **optional** = field missing in at least one sample. Generated Pydantic models use `Field(...)`-style metadata and `Optional`/`| None` accordingly.

### State file

The **state file** (e.g. `.pydanticforge/state.json`) stores the inferred type graph (the internal representation), not the generated Python. You can:

- **Generate** models from that state later without re-reading all JSON.
- **Monitor** a directory: compare new JSON against this state and optionally **autopatch** (merge new types into state and regenerate models).

### Drift

**Drift** means “this JSON does not match the schema we inferred.” The monitor compares each file’s inferred type against the expected type (from state). It reports:

- Type mismatches (e.g. expected `int`, got `str`).
- Missing required fields.
- New fields (informational).

With `--autopatch`, the state is updated by joining the observed type into the expected type, and you can write updated models to a file.

### Semantic diff

The **diff** command parses two Pydantic model **files** (AST), extracts class and field names, types, and required/optional, and compares them:

- **Breaking**: removed class/field, required field added, type narrowed (e.g. `str` → `int`), optional → required.
- **Non-breaking**: new optional field, new class, type widened (e.g. `int` → `int | str`), required → optional.

So you can use it in CI or reviews to see if a schema change might break consumers.

## Implementation details by command

This section explains how each command is implemented internally and what it is best used for.

### `watch`

- Implementation: reads stdin via `iter_json_from_stream`, calls `TypeInferer.observe` per sample, and periodically emits model code with `generate_models`.
- Persistence: always writes state with `save_schema_state`; can also export JSON Schema.
- Best use case: long-running NDJSON stream ingestion where model shape evolves over time.

### `generate`

- Implementation: builds root type from one of four sources (stdin, files/directories, state, JSON Schema), then renders deterministic Pydantic code.
- Core guarantee: deterministic output ordering for classes and fields for stable diffs in CI.
- Best use case: one-shot model generation from payload samples or existing schema assets.

### `monitor`

- Implementation: scans JSON files, infers observed types, compares against expected state with `detect_drift`, and classifies event severity.
- Operational semantics: `--fail-on` controls CI exit behavior (`none`, `breaking`, `any`) with explicit exit codes.
- Best use case: schema-drift gates in CI or periodic log-directory audits.

### `diff`

- Implementation: parses both model files using AST, normalizes model/field signatures, and computes semantic changes.
- Classification: breaking vs non-breaking is based on field/class changes and type widening/narrowing.
- Best use case: release and PR checks for backward-compatibility impact.

### `status`

- Implementation: reads state and emits deterministic state hash plus schema node/field counts; optional drift snapshot is generated with `monitor_directory_once`.
- CI value: stable machine-readable snapshots for audit trails and schema-regression baselines.

### `schema`

- Implementation: round-trips internal state <-> JSON Schema through dedicated conversion utilities.
- Interop value: enables coexistence with JSON Schema-first tooling while preserving pydanticforge workflow.

---

## Commands in detail

### `watch` — Infer schema from a live stream

Reads **newline-delimited JSON (NDJSON)** from stdin and incrementally updates the inferred schema. Optionally writes models and state periodically or at the end.

```bash
pydanticforge watch --input stdin [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--input` | Input source; only `stdin` is supported. |
| `--output` | Write generated Pydantic models to this file. If omitted, prints to stdout. |
| `--state` | Path to state file (default: `.pydanticforge/state.json`). |
| `--root-name` | Name of the root model class (default: `PydanticforgeModel`). |
| `--every N` | Emit models every N samples (0 = only at end). |
| `--strict-numbers` | Keep `int` and `float` distinct (union) instead of merging to `float`. |
| `--export-json-schema` | Also write inferred schema as JSON Schema. |
| `--json-schema-title` | JSON Schema title (default: `PydanticforgeSchema`). |

**Example: stream API responses and update models every 100 records**

```bash
tail -f api_responses.ndjson | pydanticforge watch --input stdin --output models.py --state .pydanticforge/state.json --every 100
```

---

### `generate` — Generate Pydantic models from schema

Infers schema from stdin, from file(s)/directory(ies), from a saved state file, or from JSON Schema; then writes Pydantic v2 model code.

```bash
pydanticforge generate [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--input` | JSON file or directory (repeat for multiple). Reads all `.json` files (recursive if directory). |
| `--from-state` | Use this state file instead of inferring from input. |
| `--from-json-schema` | Use this JSON Schema file as input. |
| `--output` | Output path for generated `models.py`. If omitted, prints to stdout. |
| `--save-state` | After inferring, save state to this path. |
| `--export-json-schema` | Also export inferred schema as JSON Schema. |
| `--json-schema-title` | JSON Schema title for export (default: `PydanticforgeSchema`). |
| `--root-name` | Root model class name (default: `PydanticforgeModel`). |
| `--strict-numbers` | Keep `int` and `float` as union. |

**Examples**

From stdin (e.g. NDJSON):

```bash
cat events.ndjson | pydanticforge generate --output models.py --save-state .pydanticforge/state.json
```

From a single file or directory:

```bash
pydanticforge generate --input ./samples/data.json --output models.py
pydanticforge generate --input ./samples/ --output models.py
```

From previously saved state (no JSON needed):

```bash
pydanticforge generate --from-state .pydanticforge/state.json --output models.py
```

From JSON Schema:

```bash
pydanticforge generate --from-json-schema schema.json --output models.py
```

---

### `monitor` — Scan directory for schema drift

Scans a directory for `.json` files, infers type from each file’s content, and compares to the expected schema from the state file. Reports drift (type mismatches, missing required fields, new fields). Optionally updates state and regenerates models (autopatch).

```bash
pydanticforge monitor <directory> [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `directory` | Directory to scan (required). |
| `--state` | State file path (default: `.pydanticforge/state.json`). If it doesn’t exist, first file(s) establish the baseline. |
| `--model-output` | If set, and `--autopatch` is used, write updated models here. |
| `--export-json-schema` | If set with `--autopatch`, write merged schema as JSON Schema. |
| `--json-schema-title` | JSON Schema title for export (default: `PydanticforgeSchema`). |
| `--root-name` | Root model name for generated code. |
| `--recursive` / `--no-recursive` | Scan subdirectories (default: recursive). |
| `--autopatch` | Merge drifted types into state and save; if `--model-output` is set, regenerate models. |
| `--strict-numbers` | Use strict number handling when joining types. |
| `--format` | Output format: `text` or `json`. |
| `--fail-on` | Exit threshold: `none`, `breaking`, or `any`. |

**Examples**

Report drift only:

```bash
pydanticforge monitor ./logs/api_responses --state .pydanticforge/state.json
```

Auto-update state and models when drift is found:

```bash
pydanticforge monitor ./logs --state .pydanticforge/state.json --autopatch --model-output models.py
```

CI-style failure on drift severity:

```bash
pydanticforge monitor ./logs --state .pydanticforge/state.json --format json --fail-on breaking
```

Monitor exit codes:

- `0`: no threshold reached
- `20`: warnings found and `--fail-on any`
- `21`: breaking drift found and `--fail-on breaking|any`

---

### `diff` — Semantic diff between two model files

Parses two Python files containing Pydantic `BaseModel` classes and prints a semantic diff (added/removed classes and fields, required/optional and type changes), classified as breaking or non-breaking.

```bash
pydanticforge diff <old_model.py> <new_model.py> [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--format` | Output format: `text` or `json`. |
| `--fail-on-breaking` | Exit with code 1 if any change is breaking (useful in CI). |

**Example**

```bash
pydanticforge diff models_v1.py models_v2.py
pydanticforge diff models_v1.py models_v2.py --format json
pydanticforge diff models_v1.py models_v2.py --fail-on-breaking
```

Example output:

```
[breaking] User.email: Field removed
[non-breaking] User.avatar_url: New optional field
[breaking] User.id: Type narrowed: int -> str
```

---

### `status` — Deterministic state/drift snapshot for CI

Emits a deterministic summary of schema state (including a stable hash), and optionally a drift snapshot for a directory.

```bash
pydanticforge status [directory] [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `directory` | Optional directory to include a drift snapshot in the status payload. |
| `--state` | State file path (default: `.pydanticforge/state.json`). |
| `--recursive` / `--no-recursive` | When `directory` is provided, scan recursively (default: recursive). |
| `--strict-numbers` | Use strict number handling for optional drift snapshot. |
| `--format` | Output format: `text` or `json`. |
| `--output` | Write the report to a file instead of stdout. |

**Example**

```bash
pydanticforge status ./logs --state .pydanticforge/state.json --format json --output schema_status.json
```

---

### `schema` — Convert between state and JSON Schema

Converts pydanticforge internal state files and JSON Schema documents in either direction.

```bash
pydanticforge schema [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--from-state` | Input state file. |
| `--from-json-schema` | Input JSON Schema file. |
| `--to-state` | Output state file. |
| `--to-json-schema` | Output JSON Schema file. |
| `--json-schema-title` | Title to use when writing JSON Schema (default: `PydanticforgeSchema`). |

**Examples**

```bash
pydanticforge schema --from-state .pydanticforge/state.json --to-json-schema schema.json
pydanticforge schema --from-json-schema schema.json --to-state .pydanticforge/state.json
```

---

## Use cases and examples

### 1. API response models

You have an API that returns JSON with inconsistent fields:

```json
{"user_id": 1, "name": "Alice"}
{"user_id": "2", "name": "Bob", "email": "bob@example.com"}
```

Save samples to `api_samples.ndjson`, then:

```bash
cat api_samples.ndjson | pydanticforge generate --output api_models.py --save-state .pydanticforge/state.json
```

Use the generated module in your code:

```python
from api_models import PydanticforgeModel

data = {"user_id": 1, "name": "Alice"}
obj = PydanticforgeModel.model_validate(data)
```

### 2. Log or event directory

New JSON log files are written to `./logs`. You want to detect when the “shape” of logs changes:

```bash
# One-time: build initial state from existing logs
pydanticforge generate --input ./logs --output models.py --save-state .pydanticforge/state.json

# Periodically or in CI: check for drift
pydanticforge monitor ./logs --state .pydanticforge/state.json

# Or auto-merge new shapes and refresh models
pydanticforge monitor ./logs --state .pydanticforge/state.json --autopatch --model-output models.py
```

### 3. LLM or user JSON

Pipe NDJSON from any source (script, API, LLM output) into `generate` or `watch`:

```bash
python my_script.py | pydanticforge generate --output models.py
```

### 4. CI: fail on breaking schema changes

Generate `models_v1.py` from the main branch and `models_v2.py` from a feature branch (or from two commits). Then:

```bash
pydanticforge diff models_v1.py models_v2.py --fail-on-breaking
```

If the diff contains any breaking change, the command exits with 1 so your CI can fail the build.

### 5. Nested and optional fields

Pydanticforge infers nested objects and optional fields from multiple samples. For example:

```bash
echo '{"id": 1, "meta": {"tag": "alpha"}}
{"id": 2.0, "meta": {"tag": "beta", "score": 10}}' | pydanticforge generate --output models.py
```

The root model will have `id: float`, and a nested `meta` object with `tag` (required) and `score` (optional). Generated nested objects become separate Pydantic model classes when needed.

---

## Programmatic API

You can use pydanticforge inside your own Python code instead of the CLI.

## Public API method reference

Each public method below should always have at least one runnable example in README when behavior changes.

| Method | Purpose | Key internals | Typical use case |
|---|---|---|---|
| `TypeInferer.observe` / `observe_many` | Incrementally infer type graph from JSON values. | Lattice join (`join_types`) over inferred nodes. | Build schema from stream or batched payloads. |
| `generate_models` | Emit deterministic Pydantic v2 model code from inferred root node. | Stable naming/order via model generation modules. | Materialize `models.py` for application validation. |
| `save_schema_state` / `load_schema_state` | Persist and restore inference state. | Canonical serialized IR payload with version tag. | Reuse schema without reprocessing all samples. |
| `schema_state_hash` | Compute deterministic hash of state payload. | Canonical JSON serialization + SHA-256. | CI snapshots and schema-baseline tracking. |
| `save_json_schema` / `load_json_schema` | Convert between internal state and JSON Schema files. | Explicit node-level conversion rules. | Interop with external schema tooling. |
| `monitor_directory_once` | Scan directory and detect drift against expected state. | Sample inference + `detect_drift` event generation. | CI drift checks or scheduled production audits. |
| `diff_models` / `format_diff` | Semantic diff between Pydantic model files. | AST parsing + field/type requiredness comparison. | Breaking-change review before release. |

### Infer schema and generate code

```python
from pathlib import Path
from pydanticforge.inference.infer import TypeInferer
from pydanticforge.modelgen.emit import generate_models
from pydanticforge.state import save_schema_state, load_schema_state

# From in-memory samples
inferer = TypeInferer()
inferer.observe({"id": 1, "name": "Alice"})
inferer.observe({"id": 2, "name": "Bob", "email": "bob@example.com"})
root = inferer.root  # TypeNode | None

if root is not None:
    code = generate_models(root, root_name="User")
    Path("models.py").write_text(code)
    save_schema_state(Path(".pydanticforge/state.json"), root)
```

### Load state and generate without re-inferring

```python
from pathlib import Path
from pydanticforge.state import load_schema_state
from pydanticforge.modelgen.emit import generate_models

root = load_schema_state(Path(".pydanticforge/state.json"))
code = generate_models(root, root_name="User")
Path("models.py").write_text(code)
```

### Export or import JSON Schema

```python
from pathlib import Path
from pydanticforge.json_schema import load_json_schema, save_json_schema
from pydanticforge.state import load_schema_state

root = load_schema_state(Path(".pydanticforge/state.json"))
save_json_schema(Path("schema.json"), root, title="MySchema")

round_tripped = load_json_schema(Path("schema.json"))
```

### Monitor a directory and get drift report

```python
from pathlib import Path
from pydanticforge.state import load_schema_state
from pydanticforge.monitor.watcher import monitor_directory_once

state_path = Path(".pydanticforge/state.json")
expected = load_schema_state(state_path) if state_path.exists() else None

new_root, report = monitor_directory_once(
    Path("./logs"),
    expected_root=expected,
    recursive=True,
    autopatch=False,
)

print(f"Scanned {report.files_scanned} files, drift in {report.files_with_drift}")
for fd in report.drifts:
    print(f"  {fd.path}")
    for ev in fd.events:
        print(f"    [{ev.kind}] {ev.path}: expected {ev.expected}, observed {ev.observed}")
```

### Semantic diff between two model files

```python
from pathlib import Path
from pydanticforge.diff.semantic import diff_models, format_diff

entries = diff_models(Path("models_v1.py"), Path("models_v2.py"))
print(format_diff(entries))
breaking = [e for e in entries if e.severity == "breaking"]
```

### Strict numbers

To keep `int` and `float` as a union instead of merging to `float`:

```python
inferer = TypeInferer(strict_numbers=True)
```

Use the same `strict_numbers` when calling `join_types` (e.g. in monitor autopatch) for consistency.

---

## Input and output formats

- **Stdin (watch / generate):** Newline-delimited JSON (NDJSON). Each line is one JSON value (object or array). If a line is an array, each element is treated as a separate sample.
- **Files:** `.json` files. Content can be a single JSON value (object or array) or NDJSON; arrays are expanded into one sample per element.
- **State file:** JSON file with `schema_version` and `root` (internal type graph). Do not edit by hand; use CLI or `save_schema_state` / `load_schema_state`.
- **JSON Schema:** Draft 2020-12 document import/export for state interop (`schema`, `generate`, `watch`, `monitor`).
- **Monitor JSON report:** `monitor --format json` emits machine-readable summary + per-file/per-event severities.
- **Status report:** `status --format json` emits deterministic schema metadata (`state_hash`, counts) and optional drift snapshot.
- **Generated models:** Valid Python with Pydantic v2 `BaseModel` (and optionally `RootModel` for non-object roots), `ConfigDict(extra="allow")`, and deterministic field order.

## Open source standards

Project standards expected for open-source maintainability:

- **Versioning:** semantic versioning (`MAJOR.MINOR.PATCH`), with `__version__` and `pyproject.toml` kept in sync.
- **Documentation drift policy:** any behavior/dependency/API change must update README examples and method reference in the same PR.
- **License:** MIT (`LICENSE`).
- **Citation metadata:** `CITATION.cff` maintained for academic/professional attribution.

---

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

Quality checks:

```bash
ruff check .
ruff format --check .
mypy src
pytest -q
pip-audit
```

---

## License

MIT
