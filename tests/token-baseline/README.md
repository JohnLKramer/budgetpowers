# Token baseline harness

Budgetpowers changes are hard to judge on cost. A skill edit can make a session cheaper or more
expensive by dollars, and nothing in a normal session tells you which. This harness runs a fixed
build headlessly through the full budgetpowers flow (brainstorm → spec → plan → subagent-driven
execution → finish) and reports exactly where the tokens and dollars went. Run it before and after
a change and diff the two `metrics.json` files.

- [Quickstart](#quickstart)
- [Methodology](#methodology)
- [Prompts](#prompts)
- [Outputs](#outputs)
- [Validity limits](#validity-limits)
- [Transcript facts this relies on](#transcript-facts-this-relies-on)

## Quickstart

```bash
# from the repo root; Docker must be running for crud
tests/token-baseline/run.sh smoke 3        # ~$0.20 check that the harness works
tests/token-baseline/run.sh gridworld      # default cap $50
tests/token-baseline/run.sh crud

# re-analyze an existing run
cd tests/token-baseline && uv run --python 3.12 -m analyze ../../scratch/claude-work/<run>

# harness unit tests
cd tests/token-baseline && uv run --python 3.12 --with pytest pytest tests -q
```

Runs are written to `scratch/claude-work/<app>-<YYYYMMDD-HHMM>/`, which is gitignored. The
baseline taken on 2026-10-27 against v7.0.1 is `gridworld-20261027-0034` and `crud-20261027-0034`.

The runner launches unattended Claude Code sessions with `--permission-mode bypassPermissions`.
They can run any shell command, starting from the run's `app/` directory. Auto mode blocks this
unless you add an allow rule for the script, for example
`Bash(/abs/path/to/tests/token-baseline/run.sh:*)` in your Claude Code settings.

## Methodology

### The driver (`run.sh`)

1. **A fresh repo per run.** `app/` gets `git init` and one empty commit, so the build's branches
   and worktrees stay out of this repo.
2. **Turn 1** sends `prompts/<app>.md`. **Every later turn** runs `claude -p --resume <session>`
   with a canned reply, so each turn's content comes only from the framework and the fixed prompt:
   > Approved. Choose your recommended option and continue. When the plan asks for an execution
   > method, choose subagent-driven development.

   Once finishing-a-development-branch has run and the agent asks about merging or a PR, the next
   reply is `Keep the branch as-is.`
3. **Every turn** uses `--model claude-opus-5-5 --output-format stream-json --verbose`, the
   isolation flags below, `--max-budget-usd <budget>`, and `< /dev/null`.
4. **Stop conditions**, recorded as `stop_reason` in `driver.log`:

   | Reason | When |
   |---|---|
   | `done` | finishing-a-development-branch has run and the last result has no `?`, **or** 2 consecutive turns had no tool call and no `?` (trivial tasks never reach the finishing step) |
   | `turn-cap` | 25 turns |
   | `budget` | cumulative `total_cost_usd` ≥ budget |
   | `error:…` | a non-zero exit, or a resume that returns a different session id |

5. **After stopping**, the driver:
   - copies the main transcript and `subagents/` into `transcripts/`;
   - runs the app's tests in the build's worktree (the one non-main worktree, or `app/` if there is
     none) and writes `outcome.json`;
   - runs the analyzer.

### Isolation

The measurement has to see only this repo's budgetpowers. Hooks must stay on, because budgetpowers
loads `using-budgetpowers` through a SessionStart hook, so `--bare` can't be used. Instead, each
turn passes:

```
--plugin-dir <repo root> --setting-sources project --strict-mcp-config
--settings tests/token-baseline/isolation-settings.json
```

`isolation-settings.json` excludes `~/.claude/CLAUDE.md` and disables the built-in
`cc-plugin-agents-md` plugin. Without that second setting, the same instructions arrive through
`~/AGENTS.md`. Probes on 2026-10-27 showed this cut the opening context from 10.4k to 5.8k tokens,
with the budgetpowers bootstrap still present.

The analyzer fails the run, naming each offender, when the stream's `init` event shows any of:

- a plugin other than budgetpowers loaded from this repo, or a `@builtin` plugin;
- `cc-plugin-agents-md`;
- a namespaced skill outside `budgetpowers:`;
- an MCP server;
- a missing `budgetpowers:using-budgetpowers`.

### Attribution (`analyze/`)

- **Usage** is read from every assistant record in the main and subagent transcripts, counted
  **once per `message.id`** (`usage.py`).
- **Phase.** The session starts in `brainstorm` and moves forward on the first `Write` under
  `docs/budgetpowers/specs/` (→ `spec`). After that it moves on Skill invocations:
  - writing-plans → `plan`
  - subagent-driven-development or executing-plans → `execute`
  - requesting-code-review → `review`
  - finishing-a-development-branch → `finish`

  Phases never move backwards. A subagent inherits the phase of the main-loop call that dispatched
  it, matched through `.meta.json` `toolUseId` (`attribute.py`).
- **Role** comes from the dispatch description:
  - `^Implement` → implementer
  - `^Review Task` → task-reviewer
  - `^Re-review` → re-reviewer
  - `^Fix` → fixer
  - `final` or `^Review code changes` → final-reviewer
  - anything else → `other:<description>`
- **Contributors** (`contributors.py`):
  - **Skill text loaded:** the SessionStart hook attachment, the meta record after a slash command,
    and Skill tool results.
  - **Tool results:** the 20 largest.
  - **Repeat reads:** files the same actor read more than once.
  - **Subagent briefs:** the size of each dispatch.
  - **Main-loop calls per phase.**

### Pricing and the cross-check

`prices.json` holds the $/MTok rates for input, output, cache read, and 5-minute and 1-hour cache
writes:

| Model | Source of the rates | Checked against |
|---|---|---|
| Opus 5.5 | claude-api skill pricing | matched Claude Code's per-model `costUSD` exactly |
| Sonnet 5.5 | cache read set to **$0.10**, not the skill's $0.20 | solved from two runs' `costUSD` with identical token counts |
| Haiku 5.5 | claude-api skill pricing; cache read assumed 0.1× input | no run has used Haiku yet |

Every analysis compares the computed total with Claude Code's own `total_cost_usd` from the last
turn. That figure is cumulative across `--resume`, so it is not summed per turn. The run **fails if
the two differ by more than 2%**, which is what caught the Sonnet price.

### Outcome check

| App | Command (run in the build's worktree) |
|---|---|
| gridworld | `uv run pytest` |
| crud | `export JAVA_HOME=$HOME/.sdkman/candidates/java/current && docker compose up -d && ./gradlew --gradle-user-home /Users/john.kramer/.gradle test` |
| smoke | `test -f hello.txt` |

A run whose tests fail is recorded as failed. A cheaper failed run never counts as a saving.

## Prompts

Each file in `prompts/` is the first message of a run. The text below is verbatim.

**`prompts/crud.md`**

```
/budgetpowers:brainstorming

Build a Spring Boot 3 (Kotlin, Gradle) CRUD REST app for one entity `item` stored in Postgres: columns id (PK), quantity (integer, must be >= 0), code (string, alphanumeric only, required). Endpoints: create, get by id, list, update, delete. Return 400 on validation failure, 404 on missing id. Provide the PG schema as a Flyway migration and a docker-compose.yml running Postgres. Tests with JUnit 5 (Testcontainers or the compose DB).
```

**`prompts/gridworld.md`**

```
/budgetpowers:brainstorming

Build a Python 3.12 project `gridworld`: a deterministic grid simulation. A rectangular grid (configurable width/height) has walls, a goal cell, and one agent. The agent takes actions up/down/left/right; moves into walls or off-grid leave it in place. Each step returns (state, reward, done): -1 per step, +10 on reaching the goal. Load the grid from a simple text map (`#` wall, `A` agent, `G` goal, `.` empty). Provide a CLI that runs a given action sequence or a random policy with a seed and prints the grid each step. pytest tests, uv/pyproject layout, no external runtime deps.
```

**`prompts/smoke.md`**

```
/budgetpowers:brainstorming

Add a hello.txt containing "hi".
```

Both baseline apps exercise every phase: crud wrote a spec and gridworld skipped it. They stay small
enough that the framework's own overhead is visible next to the cost of the code.

## Outputs

| File | Contents |
|---|---|
| `driver.log` | one line per turn (session, reply, result, cumulative cost) and a final `stop_reason=` line |
| `turns/NN.jsonl` | the raw stream-json of each turn |
| `transcripts/` | the main session JSONL and `<session>/subagents/` |
| `outcome.json`, `outcome.log` | the test command, where it ran, and pass/fail |
| `metrics.json` | totals; breakdowns by phase, role, model and cost type; contributors; the reported cost; the isolation result |
| `report.md` | the same numbers as tables |

## Validity limits

- **n=1 per app.** Treat a change of less than ~15% in total cost as noise until repeated baseline
  runs measure the spread.
- **The canned reply removes the human.** Real sessions add a main-loop turn per design question,
  so the harness understates brainstorming.
- **Gradle may skip the tests.** It can report the test task up to date, so "pass" for crud can
  reflect the agent's own last test run.

## Transcript facts this relies on

These were observed in Claude Code 2.1.309. Re-check them after a Claude Code upgrade.

- Assistant messages are written as one record per content block. The records share
  `message.id` and carry identical `usage`.
- `result.total_cost_usd` and `modelUsage` are cumulative across `--resume`.
- Subagent transcripts are `<session>/subagents/agent-<id>.jsonl`. The matching `.meta.json`
  carries `description` and `toolUseId`.
- The main session writes its cache at the 1-hour rate; subagents use the 5-minute rate.
- **Known gap:** a nested subagent (`spawnDepth > 1`) makes the analyzer fail, because its
  dispatch lives in a subagent transcript.
