# Token Baseline Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a headless runner and a transcript analyzer, then use them to produce two token-usage baselines (Spring Boot CRUD and Python gridworld) and a ranked list of findings.

**Architecture:** `run.sh` drives `claude -p` turn by turn with a canned approval reply and saves each turn's stream-json. `analyze.py` reads the session's main and subagent JSONL transcripts, deduplicates usage by message id, attributes it by phase, actor and cost type, and writes `metrics.json` and `report.md`.

**Tech Stack:** bash, Python 3.12 standard library (run via `uv run --python 3.12`), pytest, and Claude Code 2.1.309 headless mode.

**Spec:** `docs/superpowers/specs/2026-10-27-token-baseline-harness-design.md`

## Global Constraints

- Everything lives under `scratch/`, which is gitignored. There are no commit steps; the run directories are the kept baseline.
- Superpowers under test: this repo (`/Users/john.kramer/source/personal/budgetpowers`, v7.0.1), loaded with `--plugin-dir`.
- Main model: `claude-opus-5-5`. Turn cap: 25. Budget cap: `--max-budget-usd 50` per app.
- Canned reply, verbatim: `Approved. Choose your recommended option and continue. When the plan asks for an execution method, choose subagent-driven development.` For the finishing step's merge/PR question, the answer is "keep the branch as-is".
- Isolation flags, verbatim: `--setting-sources project --strict-mcp-config --settings scratch/harness/isolation-settings.json`, where the file contains `{"claudeMdExcludes":["/Users/john.kramer/.claude/CLAUDE.md"],"enabledPlugins":{"cc-plugin-agents-md@builtin":false}}`. Probes on 2026-10-27 showed this keeps out `~/.claude/CLAUDE.md` and `~/AGENTS.md` while superpowers' SessionStart hook still fires. `--bare` is forbidden because it disables hooks.
- Always pass `< /dev/null` to `claude -p`.
- Fail loudly on any isolation failure, missing transcript, unparseable usage, or non-zero `claude` exit. Never substitute defaults.
- Python analyzer: standard library only.

## Transcript facts (observed, Claude Code 2.1.309)

- Main transcript: `~/.claude/projects/<encoded cwd>/<session_id>.jsonl`. Find it with the glob `~/.claude/projects/*/<session_id>.jsonl`; don't recompute the encoding (`/tmp` encodes as `-private-tmp`).
- Subagents: `<same dir>/<session_id>/subagents/agent-<id>.jsonl`, plus `agent-<id>.meta.json` with `{"agentType","description","toolUseId",...}`. `toolUseId` is the `tool_use.id` of the main-loop `Agent` call that dispatched the subagent.
- `type == "assistant"` records repeat **one record per content block, sharing `message.id`** and carrying identical `usage`. Count each `message.id` once.
- `usage` fields: `input_tokens`, `output_tokens`, `cache_read_input_tokens`, and `cache_creation.ephemeral_5m_input_tokens` / `ephemeral_1h_input_tokens`. These two cache-write rates are priced differently. `message.model` names the model.
- The stream-json `system/init` event has `plugins` (`name`, `path`, `source`), `skills`, and `mcp_servers`. The `result` event has `total_cost_usd`, `session_id`, `is_error` and `subtype`.

## Review Focus

1. **Duplicate assistant records:** if usage were summed per record instead of per `message.id`, totals would be inflated about 2×. Pinned by a test in Task 1.
2. **A subagent with no `.meta.json`, or a `toolUseId` with no matching dispatch:** this must fail loudly, not land silently in "unclassified". Pinned in Task 2.
3. **A model missing from `prices.json`** (for example a Haiku subagent): this must fail and name the model. Pinned in Task 1.
4. **Resumed turns:** `--resume` appends to the same session file, so the analyzer must see all turns in one transcript. If a resume forks to a new session id, the driver must detect it and fail. Pinned in Task 4.
5. **Computed dollars drifting from Claude Code's own `total_cost_usd`:** this shows the price table is wrong. It must fail when the difference exceeds 2%. Pinned in Task 3.

---

## Milestone 1: Harness

### Task 1: Usage loading and pricing

**Files:**
- Create: `scratch/harness/analyze/usage.py`, `scratch/harness/prices.json`
- Test: `scratch/harness/tests/test_usage.py`, fixtures in `scratch/harness/tests/fixtures/run1/`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Usage: input: int; output: int; cache_read: int; cache_write_5m: int; cache_write_1h: int` with `__add__`.
  - `@dataclass(frozen=True) class Message: id: str; model: str; usage: Usage; index: int` (`index` is the position of the message's first record in its file).
  - `load_messages(path: Path) -> list[Message]`, deduplicated by `message.id`. It raises `TranscriptError` if an assistant record lacks `usage` or `message.model`.
  - `cost_usd(model: str, u: Usage, prices: dict) -> float`. It raises `PricingError(model)` when the model is unknown.
  - The `prices.json` shape: `{"<model id>": {"input": $/MTok, "output": ..., "cache_read": ..., "cache_write_5m": ..., "cache_write_1h": ...}}`.

- [ ] **Step 1: Build the fixture.** `tests/fixtures/run1/`: one main transcript `S.jsonl` and `S/subagents/agent-a1.jsonl` + `agent-a1.meta.json`. Use real record shapes (see Transcript facts). The main file has 3 assistant messages, each split across 2 records with the same `message.id`. The first message has usage `{input 10, output 100, cache_read 1000, 5m 0, 1h 2000}`. Give the other records distinct round numbers and write the totals in a comment at the top of the test file.
- [ ] **Step 2: Write failing tests.** `test_dedupes_by_message_id` (3 messages, not 6; summed usage equals the commented total). `test_missing_usage_raises`. `test_unknown_model_raises_pricing_error`. `test_cost_uses_separate_cache_write_rates` (a hand-computed dollar value for a 5m-only usage and for a 1h-only usage).
- [ ] **Step 3: Run** `cd scratch/harness && uv run --python 3.12 --with pytest pytest tests/test_usage.py -v`. Expected: FAIL (module missing).
- [ ] **Step 4: Implement `usage.py`.** Fill `prices.json` for `claude-opus-5-5`, `claude-sonnet-5-5` and `claude-haiku-5-5` from the `claude-api` skill's pricing reference, not from memory.
- [ ] **Step 5: Run** the same command. Expected: PASS.

### Task 2: Phase and actor attribution

**Files:**
- Create: `scratch/harness/analyze/attribute.py`
- Test: `scratch/harness/tests/test_attribute.py` (extend the `run1` fixture)

**Interfaces:**
- Consumes: `load_messages`, `Message`, `Usage` from Task 1.
- Produces:
  - `PHASES = ("brainstorm", "spec", "plan", "execute", "review", "finish")`.
  - `phase_timeline(main_path: Path) -> list[tuple[int, str]]`: (record index, phase) boundaries.
  - `role_for(description: str) -> str`.
  - `attribute(session_dir: Path, session_id: str) -> list[Row]`, where `@dataclass Row: actor: str; role: str; phase: str; model: str; usage: Usage`. `actor` is `"main"` or `"agent-<id>"`.

Phase rules, checked in transcript order. The session starts in `brainstorm`. A `Write` `tool_use` whose `file_path` contains `/docs/superpowers/specs/` switches to `spec` the first time. A `Skill` `tool_use` with `input.skill` of `superpowers:writing-plans` switches to `plan`; `superpowers:subagent-driven-development` or `superpowers:executing-plans` to `execute`; `superpowers:requesting-code-review` to `review`; `superpowers:finishing-a-development-branch` to `finish`. Phases never go backwards: a later switch to an earlier phase is ignored.

Role rules, matched on the meta `description`: `^Implement` → `implementer`; `^Review Task` → `task-reviewer`; `^Re-review` → `re-reviewer`; `^Fix` → `fixer`; contains `final` (case-insensitive) or `^Review code changes` → `final-reviewer`; anything else → `other:<description>`. The main loop's role is `main`. A subagent's phase is the phase in effect at the main-loop record holding the `tool_use.id` equal to its `toolUseId`.

- [ ] **Step 1: Write failing tests.** `test_phase_switches_on_skill_and_spec_write`. `test_phase_never_regresses`. `test_role_for` (one case per rule). `test_subagent_inherits_dispatch_phase`. `test_subagent_without_meta_raises`. `test_unmatched_tool_use_id_raises`.
- [ ] **Step 2: Run** `uv run --python 3.12 --with pytest pytest tests/test_attribute.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement `attribute.py`.** Errors are `TranscriptError` from Task 1.
- [ ] **Step 4: Run** the same command. Expected: PASS.

### Task 3: Isolation checks, contributors, outputs, CLI

**Files:**
- Create: `scratch/harness/analyze/__main__.py`, `scratch/harness/analyze/isolation.py`, `scratch/harness/analyze/contributors.py`, `scratch/harness/analyze/report.py`
- Test: `scratch/harness/tests/test_isolation.py`, `scratch/harness/tests/test_report.py`

**Interfaces:**
- Consumes: `attribute`, `Row`, `cost_usd`.
- Produces:
  - `check_isolation(init: dict, repo_root: Path) -> None`. It raises `IsolationError` listing every offender when:
    - a plugin is not either `superpowers` with `path == repo_root` or a plugin whose `source` ends in `@builtin` (other than `cc-plugin-agents-md@builtin`);
    - a skill contains `:` but does not start with `superpowers:`;
    - `mcp_servers` is non-empty;
    - `superpowers:using-superpowers` is absent from `skills`.
  - `contributors(session_dir, session_id) -> dict` with these keys:
    - `skill_loads`: skill → [count, total bytes of the tool_result that followed];
    - `top_tool_results`: the 20 largest, each `{tool, bytes, actor}`;
    - `repeat_reads`: path → count, for paths read more than once by the same actor;
    - `briefs`: agent id → prompt bytes from its first user record;
    - `turns_per_phase`.
  - CLI: `uv run --python 3.12 -m analyze <run-dir>` (run from `scratch/harness`). It reads `<run-dir>/turns/*.jsonl` (stream-json; init from `01.jsonl`) and `<run-dir>/transcripts/`, then writes `<run-dir>/metrics.json` and `<run-dir>/report.md`. It exits non-zero on any error.
- `metrics.json` keys: `session_id`, `stop_reason` (read from `driver.log`), `outcome` (`{"tests": "pass"|"fail"|"not-run", "command": str}` from `<run-dir>/outcome.json`), `totals` (`{usage, usd}`), `by_phase`, `by_role`, `by_model`, `by_cost_type` (the four usage fields with their dollars), `contributors`, `claude_reported_usd` (the sum of `total_cost_usd` over the turns), `isolation: "ok"`.
- `report.md`: one table each for phase, role and cost type (tokens, $, % of $), then the contributor lists and the outcome. It starts with the line `n=1 baseline; human back-and-forth replaced by a canned reply, so brainstorm cost is understated.`

- [ ] **Step 1: Write failing tests.** `test_isolation_ok_for_probe_init` (use the plugin and skill lists observed on 2026-10-27, written into the test). `test_isolation_flags_foreign_plugin`, `..._namespaced_foreign_skill`, `..._mcp_server`, `..._agents_md_plugin`, `..._missing_bootstrap`. `test_cost_drift_over_2pct_fails` (a fixture with `claude_reported_usd` 5% off the computed total; the CLI exits non-zero naming both figures). `test_report_tables_sum_to_total` (on `run1`, the phase $ sum equals `totals.usd` within $0.001).
- [ ] **Step 2: Run** `uv run --python 3.12 --with pytest pytest tests -v`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement** the four modules.
- [ ] **Step 4: Run** `uv run --python 3.12 --with pytest pytest tests -v`. Expected: all PASS.

### Task 4: Runner and smoke run

**Files:**
- Create: `scratch/harness/run.sh`, `scratch/harness/isolation-settings.json`, `scratch/harness/prompts/crud.md`, `scratch/harness/prompts/gridworld.md`, `scratch/harness/prompts/smoke.md`

**Interfaces:**
- Consumes: the analyzer CLI from Task 3.
- Produces: `run.sh <app> [budget_usd]` (default 50). It creates `scratch/claude-work/<app>-<YYYYMMDD-HHMM>/` containing:
  - `app/`: `git init` plus one empty commit; the working directory for `claude`;
  - `turns/NN.jsonl`: each turn's stream-json;
  - `driver.log`: one line per turn (`turn=N session=<id> reply=<first 40 chars> result=<subtype>`), with a final `stop_reason=<done|turn-cap|budget|error:<msg>>`;
  - `transcripts/`: copies of the main JSONL and its `<session_id>/subagents/` directory.
- The prompt files contain `/superpowers:brainstorming` on line 1, then the task text from the spec's "Fixed prompts" section, verbatim. `smoke.md` is `/superpowers:brainstorming` followed by `Add a hello.txt containing "hi".`

Loop behavior:
- Turn 1 sends the prompt file. Each later turn runs `claude -p --resume <session_id>` with the canned reply. Every turn passes the Global Constraints flags plus `--output-format stream-json --verbose --model claude-opus-5-5 --max-budget-usd <remaining>`, where remaining is the budget minus the summed `total_cost_usd` so far.
- Stop conditions:
  - `done`: the result text contains no `?`, and the finishing-a-development-branch Skill has run in the transcript. Check this with `grep -q '"skill":"superpowers:finishing-a-development-branch"'` on the main JSONL.
  - `turn-cap` at 25.
  - `budget` when remaining is ≤ 0.
  - Any `claude` exit that isn't zero, or a `result.session_id` that differs from turn 1's, stops with `error`.
- When the stop reason is `done`, the run ends with one more canned turn: `Keep the branch as-is.`, but only if the last result asks about merging or a PR (it matches `-i 'merge|pull request|PR'`).
- After stopping, copy the transcripts. Then run the outcome check: `gridworld` → `uv run pytest` in `app/`; `crud` → `docker compose up -d` and then `./gradlew --gradle-user-home /Users/john.kramer/.gradle test` in `app/`; `smoke` → `test -f hello.txt`. Write `outcome.json`, then run the analyzer.

- [ ] **Step 1: Write the four prompt files and `isolation-settings.json`,** with content verbatim from the spec and Global Constraints.
- [ ] **Step 2: Implement `run.sh`** with `set -euo pipefail`.
- [ ] **Step 3: Smoke run.** `scratch/harness/run.sh smoke 3`. Expected: `driver.log` ends with `stop_reason=done` or `turn-cap`; `transcripts/` holds the main JSONL; `metrics.json` exists with `isolation: "ok"` and `claude_reported_usd` within 2% of `totals.usd`; and `driver.log` shows the same session id on every turn. The smoke run goes through the full brainstorm → plan → SDD flow, so the $3 cap may stop it early. That's acceptable as long as at least 2 turns ran.
- [ ] **Step 4: Fix the harness until Step 3 passes.** Do not fix it by loosening a check.

## Milestone 2: Baseline

### Task 5: Baseline runs

**Files:** generated only, under `scratch/claude-work/crud-*/` and `scratch/claude-work/gridworld-*/`.

- [ ] **Step 1:** Confirm Docker is up (`docker info`). If it isn't, start it with the `executing-apps` skill.
- [ ] **Step 2:** Run `scratch/harness/run.sh crud` in the background. Wait for it to finish. Expected: `metrics.json` and `report.md` are written, and `stop_reason` is recorded. If it stops with `budget` before `finish`, report that to your human partner before re-running with a higher cap.
- [ ] **Step 3:** Run `scratch/harness/run.sh gridworld` the same way.
- [ ] **Step 4:** Check both `outcome.json` files. A failed test outcome is recorded as is, and the run stays in the baseline marked failed.

### Task 6: Findings

**Files:**
- Create: `scratch/claude-work/baseline-findings.md`

- [ ] **Step 1: Write the findings from the two `metrics.json` files only.**
  - Open with a totals table per app: $, tokens by cost type, turns, subagent count, and outcome.
  - Then rank the token sinks across both apps by share of $. Each row carries:
    - the sink, with its metric citation (`<run>/metrics.json:<key path>`);
    - the skill or rule responsible, with its `skills/<name>/<file>:<line>`;
    - the proposed relaxation or simplification;
    - the expected saving in $ and %, with the arithmetic shown;
    - the quality risk.
  - State the validity limits from the spec.
- [ ] **Step 2: Self-check.** Every number in the findings appears in a `metrics.json`. Every proposal names a file and line that exists.
