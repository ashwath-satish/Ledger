# LEDGER — a compiler for the world's most-used programming language

**Excel is the most widely deployed programming language on earth. It has no types, no tests, no version control, and no code review. Roughly 90% of spreadsheets contain errors, and companies run on them anyway.**

LEDGER treats a spreadsheet as what it actually is — a program — and does to it what we do to every other program: parse it, build its dependency graph, run static analysis over it, and compile it to typed, tested, reviewable Python.

---

## What it does

Drop in an `.xlsx`. LEDGER:

1. **Parses** every formula into an AST of cell references and ranges.
2. **Builds the dependency DAG** — 24 cells, 51 edges on the demo sheet.
3. **Runs a static audit** and finds classes of bug that are structurally invisible inside Excel:

| Check | What it catches |
|---|---|
| `CYCLE` | Circular references. Excel silently returns a stale iterate; the number on screen is not a computation, it's an accident. |
| `RANGE` | `SUM()` that doesn't cover its own data. Someone added rows; the range never grew. **Rows vanish from totals silently.** |
| `PATTERN` | A formula that breaks its column's own pattern. Detected by normalising every formula to R1C1-relative form: `=B2*C2` in D2 and `=B3*C3` in D3 are *the same formula*. `=B8*C7` in D8 is not. This is what a copy-paste landing one row off looks like. |
| `ORPHAN` | Data that no formula reads. Dead input — or the fingerprint of a reference that went somewhere else. |
| `MAGIC` | A constant hardcoded into N separate formulas, with no single place to change it. |

4. **Topologically sorts** the DAG and **emits a Python module** — one line per cell, in dependency order, plus a frozen `Inputs` dataclass for the actual data.
5. **Emits a pytest regression suite** that pins every cell to the value Excel had cached. The spreadsheet now has a safety net it never had: refactor it, and anything that moves, fails.

## The moment it clicks

The demo sheet contains a real bug at D8. In Excel it reads:

```
=B8*C7
```

Which looks like nothing. It produces a plausible number. Nobody will ever catch it.

LEDGER compiles that same cell to:

```python
motor_24v_line_total = motor_24v_units * bearing_6203_unit_cost   # D8: =B8*C7
```

**You are multiplying motor units by bearing cost.** The bug didn't change. The *representation* changed, and the bug became impossible to miss. That is the entire argument for compiling spreadsheets, in one line.

And independently, from the other direction, the compiler reports:

```
[ERROR] ORPHAN — Data that nothing reads: C8
```

Because if D8 never reads C8, the motor's unit cost is dead data. Two orthogonal analyses, same bug, neither one knowing about the other.

---

## Where the model goes — and where it deliberately doesn't

We use [Featherless](https://featherless.ai) for inference. **The model is never asked to do arithmetic, and it never touches the parser, the DAG, the audit, or the codegen.** All of that is deterministic and runs with the network off. An LLM that hallucinates one cell reference produces a compiler that is worse than useless.

The model is called *afterwards*, on the artifacts, to do the one job a parser fundamentally cannot: **read the human meaning that lives in the headers.**

- **Naming.** A parser knows `D8`. It cannot know `D8` is *the motor's line total* — that fact exists only in the prose of column D's header and column A's row label. The model reads the sheet's labels and returns Python identifiers. This is what makes the bug above legible; with `d8 = b8 * c7` it stays invisible.
- **Explanation.** Each defect gets one sentence on what the author was *trying* to do, and one on what it costs. Static analysis says `SUM(D2:D10) excludes D11`. The model says *someone added a line item and the total never noticed — you are under-reporting by $352.*
- **Invariants.** The model proposes business rules the formulas never state ("a line total is never negative", "the sum of parts equals the whole"), which we emit as extra pytest cases. **The model proposes; the compiler disposes** — every proposed assertion is validated as a single well-formed Python assertion before it survives into the test file.

That's the thesis: **deterministic where correctness is checkable, model where meaning is required.** Nothing the model says can corrupt the compilation.

### Two models, routed by task

The strongest use of a large model catalog is *routing*, not picking one model and hoping.

| Pass | Job | Model |
|---|---|---|
| Naming, invariants | Emit snake_case Python identifiers and syntactically valid `assert` lines | `Qwen2.5-Coder-32B-Instruct` — a code task, so a code model |
| Explanations | Explain a defect to the person who owns the numbers | `Qwen2.5-72B-Instruct` — a prose task; coder models write stilted prose |

**We deliberately do not use vision or embeddings, and both omissions are load-bearing.** A screenshot of a spreadsheet shows *values*, not *formulas* — `=B8*C7` renders as `1520`, so the entire bug class we catch is invisible to a camera. We read the XML inside the `.xlsx`, where the formulas actually live. And formula equivalence is *exact*, not fuzzy: R1C1 normalisation reduces it to a string compare, so reaching for cosine similarity would be a strict downgrade from `===`.

---

## Known scope

Stated plainly, because a compiler that hides its limits is a compiler you can't trust:

- **Single sheet.** Cross-sheet references are parsed, then dropped.
- **Partial formula grammar.** Arithmetic and `SUM/AVERAGE/MIN/MAX/COUNT/ABS/ROUND` compile properly. `IF`, `VLOOKUP`, `INDEX/MATCH` are emitted with a `# TODO(ledger)` marker rather than silently mistranslated — a wrong translation is worse than an honest gap.
- **The regression suite pins current behaviour, bugs included.** That is what a regression harness is *for*: the sheet's behaviour is now something you can diff.

---

## Run it

```bash
open index.html          # no build step, no npm, works offline
```

Click **Load the demo ledger** → **Compile**. That path requires no API key and no network.

For the semantic layer, open **Inference settings** and paste a Featherless key. If the browser blocks the cross-origin call from `file://`:

```bash
pip install flask requests
python proxy.py
# then point the endpoint at http://localhost:8787/v1/chat/completions
```

## Stack

Vanilla JS, zero dependencies except SheetJS for `.xlsx` unpacking. The parser, R1C1 normaliser, three-colour cycle detector, Kahn topological sort, and Python codegen are all written from scratch and total ~400 lines. Featherless for the semantic layer.

## What's next

- Multi-sheet scope (currently single-sheet)
- Full formula grammar (`IF`, `VLOOKUP`, `INDEX/MATCH` → real Python)
- `git diff` for workbooks: compile both revisions, diff the *modules*
- CI action: compile every spreadsheet in a repo, fail the build on a new `CYCLE` or `RANGE`
