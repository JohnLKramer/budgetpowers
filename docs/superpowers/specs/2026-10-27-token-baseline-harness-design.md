# Token Baseline Harness — Design

## Goal

Superpowers spends more tokens than its results justify. Before changing any
skill, measure where the tokens go on two small, representative builds, keep
those measurements as the baseline, and propose relaxations or
simplifications ranked by how much they would save.

This phase changes no skills. Its deliverables are a repeatable harness, two
baseline runs, and a ranked proposal that becomes the next spec.

## Decisions already made

| Question | Decision |
|---|---|
| Superpowers under test | Upstream v7.0.1, this repo (`budgetpowers`), loaded with `--plugin-dir` |
| How builds run | Headless `claude -p`, one session per app, resumed turn by turn |
| Execution method at the writing-plans handoff | Subagent-driven development |
| Model | Opus 5.5 (`claude-opus-5-5`) for the main loop; subagent models are whatever the framework picks |
| Runs per app | One for the baseline (n=1) |
| Location | `scratch/` at the repo root, ignored by git |

## Layout

```
scratch/
  harness/
    run.sh            # drive one build
    analyze.py        # attribute tokens for one run
    prompts/
      crud.md
      gridworld.md
  claude-work/
    <app>-<YYYYMMDD-HHMM>/
      app/            # the build's working directory, its own git repo
      transcripts/    # copied main + subagent JSONL
      driver.log      # each turn: session id, reply sent, stop reason
      metrics.json
      report.md
```

## Fixed prompts

Each prompt starts with `/superpowers:brainstorming` and is followed by the
task text.

**crud.md** — Build a Spring Boot 3 (Kotlin, Gradle) CRUD REST app for one
entity `item` stored in Postgres: columns id (PK), quantity (integer, must be
>= 0), code (string, alphanumeric only, required). Endpoints: create, get by
id, list, update, delete. Return 400 on validation failure, 404 on missing id.
Provide the PG schema as a Flyway migration and a docker-compose.yml running
Postgres. Tests with JUnit 5 (Testcontainers or the compose DB).

**gridworld.md** — Build a Python 3.12 project `gridworld`: a deterministic
grid simulation. A rectangular grid (configurable width/height) has walls, a
goal cell, and one agent. The agent takes actions up/down/left/right; moves
into walls or off-grid leave it in place. Each step returns (state, reward,
done): -1 per step, +10 on reaching the goal. Load the grid from a simple text
map (`#` wall, `A` agent, `G` goal, `.` empty). Provide a CLI that runs a given
action sequence or a random policy with a seed and prints the grid each step.
pytest tests, uv/pyproject layout, no external runtime deps.

## Runner (`run.sh <app>`)

1. Create `scratch/claude-work/<app>-<stamp>/app/` and `git init` it, with one
   empty commit, so the build's branches and worktrees stay out of
   `budgetpowers`.
2. Start the session from `app/` with
   `claude -p --output-format stream-json --verbose --model claude-opus-5-5
   --plugin-dir <repo root> --setting-sources project --strict-mcp-config
   --max-budget-usd 50` (per app; raise it if the crud run hits the cap before finishing), passing the prompt file.
3. When a turn ends, resume it with `claude -p --resume <session-id>` and the
   canned human reply:
   > Approved. Choose your recommended option and continue. When the plan
   > asks for an execution method, choose subagent-driven development.
4. Stop when any of these happens: the agent reports the work finished and the
   finishing-a-development-branch step is done; 25 turns; the $50 cap. The
   finishing step's merge/PR question is answered "keep the branch as-is".
   Record the stop reason in `driver.log`.
5. Copy the session's main transcript and every subagent transcript from
   `~/.claude/projects/<encoded app path>/` into `transcripts/`.

The canned reply never adds requirements, so every turn's content comes from
the framework and the fixed prompt.

### Isolation

The baseline must measure only budgetpowers' superpowers. Hooks must stay on,
because superpowers injects `using-superpowers` with a SessionStart hook. So
`--bare` is not used.

`analyze.py` reads the stream's `init` event and fails, naming the offending
entries, if:

- any skill or plugin other than budgetpowers' superpowers and Claude Code
  built-ins is loaded, or
- any MCP server is connected, or
- the superpowers SessionStart context is missing from the first turn.

It records in `metrics.json` whether the user-level CLAUDE.md reached the
context. That file is not a reason to fail, but it is reported because it
adds tokens to every turn.

## Analyzer (`analyze.py <run-dir>`)

It reads every assistant message's `usage` across all transcripts, from the
main session and from subagents. It never estimates a number that the
transcript records.

**Breakdowns**

- **By phase:** brainstorm, spec, plan, execute, review, finish. A phase
  starts at the Skill invocation that opens it (brainstorming,
  writing-plans, subagent-driven-development, requesting-code-review,
  finishing-a-development-branch). Subagent usage is assigned to the phase of
  the main-loop call that dispatched it.
- **By actor:** the main loop, then each subagent grouped by role. The role
  is taken from the dispatch prompt's template heading (implementer, spec
  reviewer, code-quality reviewer, final reviewer, and so on), or
  `unclassified`.
- **By cost type:** fresh input, cache write, cache read, and output tokens,
  plus dollars at list price for each model seen.
- **Top context contributors:** bytes of skill bodies loaded (per skill, with
  repeat loads counted), the 20 largest tool results, files read more than
  once, the size of each subagent brief, and the number of turns per phase.

**Outputs**

- `metrics.json`: every number above, machine-readable, so later runs can be
  diffed against it.
- `report.md`: the same numbers as tables, plus the run's outcome (did it
  finish, do the tests pass).

**Outcome check:** after the run, the analyzer runs the app's tests (`uv run
pytest` for gridworld; `./gradlew test` for crud, after `docker compose up -d`
if the tests need the DB) and records pass or fail. A run whose tests fail is
reported as failed. A cheaper failed run never counts as a saving.

## Baseline and proposal

1. Run crud, then gridworld.
2. Commit nothing from `scratch/`. The run directories are the kept
   baseline.
3. Write `scratch/claude-work/baseline-findings.md`. It ranks the largest
   token sinks by their share of total cost, and pairs each with a proposed
   relaxation or simplification of a named skill or rule, the expected saving
   in tokens and dollars, and the risk to output quality.
4. The approved subset of that proposal becomes the next spec. Each
   accepted change is then measured with the same harness against this
   baseline.

## Validity limits

- n=1 per app. A later change that moves total cost by less than about 15% is
  treated as noise until a second run of the baseline confirms the spread.
- The canned reply removes human back-and-forth. A real session with a person
  answering questions costs more turns. The baseline therefore understates
  brainstorming's real cost, and the findings must say so.
- Cache-read tokens dominate long sessions. Dollar figures, not raw token
  counts, are the ranking key.

## Error handling

The harness fails loudly and stops on these conditions:

- an isolation check fails,
- a transcript is missing,
- a `usage` record cannot be parsed,
- `claude` exits non-zero.

It does not substitute defaults. Partial runs keep their directory, with
`driver.log` naming the stop reason.

## Testing the harness

`analyze.py` gets pytest tests. They run it against a small hand-built
fixture transcript (one main session and one subagent) with known usage
totals, and check the phase split, the role grouping, the dollar math, and
that each isolation check fails when its condition is met.
`run.sh` is verified by a smoke run with a trivial prompt and a $1 cap
before the real baseline.
