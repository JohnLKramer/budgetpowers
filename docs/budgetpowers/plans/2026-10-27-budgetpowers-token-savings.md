# Budgetpowers Token Savings (changes 1–3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut the controller turns and controller-written output that dominate SDD cost: one bookkeeping call per task boundary, dispatch prompts that point at the templates, and a builder check only for multi-component specs. Then update the docs to match and rename the product in prose from Superpowers to Budgetpowers, with a cleanup checklist for the identifiers.

**Architecture:** One new bash script (`task-next`) in `skills/subagent-driven-development/scripts/`, tested like `task-done`. The rest is wording in three skill files (SDD `SKILL.md` plus its two prompt templates, and brainstorming `SKILL.md`).

**Tech Stack:** bash, git, awk. Tests are bash in `tests/claude-code/`.

**Spec:** `scratch/claude-work/proposal.md`, changes 1–3. Change 4 (recommending a mid-tier controller or Native execution) is out of scope for this plan, and so is the final-reviewer scaling that the proposal moved to "Not proposed". The spec is git-ignored scratch, so read it from the working tree.

## Deviations from the spec

The spec disagrees with the code in three places. This plan follows the code.

1. **`task-next` does not write the review package or take a test command.** The SDD ledger line is written after the review comes back clean (`SKILL.md:307`), not when tests pass, and `review-package` is needed when the implementer reports DONE, before the review. So `task-next` bundles only what happens together at a task boundary: ledger line for the finished task, BASE, and the next brief. Its saving is about five calls per 3-task run (≈ $0.16–0.21, 5–6%), below the spec's 7–10%.
2. **The inline path for change 3 is the existing "read the document as that builder yourself" sentence** (`skills/brainstorming/SKILL.md:244`). There is no self-review checklist in that file.
3. **The reference-form dispatch keeps a one-line "you never dispatch subagents" sentence.** The spec's short form omits it, but that contract exists because workers spawning their own reviewers cost a full extra review seat per task (`SKILL.md:219-224`).
4. **The docs update (Task 5) is mostly the rename.** `README.md` and `AGENTS.md` never mention the ledger, `task-brief`, or the builder check, so Tasks 1–4 change no fact in them. `docs/testing.md` gets the one new test bullet in Task 1.
5. **The prose rename skips the sections that describe upstream.** README's Commercial Services, Installation, Community, Updating and License sections point at upstream's support address, marketplaces and repos. Calling that "Budgetpowers" would make false statements.

## Global Constraints

- Every existing check still happens; only the number of controller calls changes (spec, change 1 risk).
- New scripts fail loudly with a non-zero exit and a stderr message, matching `task-done`'s contract.
- Sibling scripts are invoked as `"${BASH:-bash}" <path>`, not exec'd directly (comment in `scripts/task-brief`, issue #2040).
- Skill wording is eval-gated (`AGENTS.md`, "Skill Changes Require Evaluation"). Tasks 2–4 end with an eval gate before they count as done.
- No new baseline runs and no Sonnet arms. Nothing here goes upstream.
- The rename covers the product name in prose only: the capitalised word "Superpowers" outside code spans, URLs and commands. Identifiers stay as they are: skill ids (`superpowers:*`, `using-superpowers`, `diagnosing-superpowers`), paths (`.superpowers/`, `docs/superpowers/`), `SUPERPOWERS_ROOT`, plugin ids, and upstream URLs (`obra/superpowers`, `superpowers-evals`). Task 6 lists them for a later pass.

## Review Focus

- `task-next --complete M` when Task M's BASE was never recorded (workspace wiped by `git clean -fdx`, or a run resumed mid-task): must exit non-zero with a message, never write a ledger line.
- A RESULT that is neither `review clean` nor `<K> parked` (for example `done`, or an empty string): must be rejected, so a typo cannot put a malformed line in the recovery ledger.
- `--start N` for a task number the plan does not contain: must exit non-zero and leave no BASE file behind.
- `--start N` run twice for the same task: must refuse rather than re-record BASE at a later HEAD, which would drop the task's earlier commits from its review range.
- `--complete M ... --start N` where the `--complete` half fails: must not start Task N.

---

## Milestone 1: One bookkeeping call per task boundary

### Task 1: `task-next` script

**Files:**
- Create: `skills/subagent-driven-development/scripts/task-next` (mode 755)
- Create: `tests/claude-code/test-sdd-task-next.sh` (mode 755)
- Modify: `docs/testing.md` (one bullet under "Plugin tests")

**Interfaces:**
- Consumes: `scripts/sdd-workspace PLAN_FILE` prints the plan's workspace dir. `scripts/task-brief PLAN_FILE N` prints `wrote <path>: <n> lines` (exit 3 if task not found).
- Produces: `task-next PLAN_FILE [--complete M RESULT] [--start N]`, at least one flag. Prints, in this order and only for the flags given:
  - `ledger: <line appended to progress.md>`
  - `brief: <path to task N's brief>`
  - `base: <full SHA of HEAD>`
  Ledger line: `Task M: complete (commits <base7>..<head7>, RESULT)`, header created as in `task-done` if the ledger is missing. BASE is stored at `<workspace>/task-N-base`. Exit codes: 2 usage or bad RESULT; 3 no recorded BASE for M, or task N not in plan; 4 `--start N` when `task-N-base` already exists.

- [ ] **Step 1: Write the failing test** in `tests/claude-code/test-sdd-task-next.sh`

Copy the skeleton of `tests/claude-code/test-executing-plans-scripts.sh` (pass/fail helpers, temp repo, `git_id`, cleanup). Fixture: `plan.md` with Tasks 1–3, committed as `base`. Tests, in order, each pass/fail on the stated assertion:

```bash
# no flags / unknown flag            -> rc == 2
# --complete 1 "done"                -> rc == 2, ledger has no "Task 1:" line   (Review Focus 2)
# --complete 1 "review clean" (no BASE recorded) -> rc == 3, no ledger line     (Review Focus 1)
# --start 9                          -> rc == 3, task-9-base absent             (Review Focus 3)
# --start 1                          -> out has "brief: $repo/.superpowers/sdd/plan/task-1-brief.md"
#                                       and "base: $base"; task-1-base contains $base
# --start 1 again                    -> rc == 4, task-1-base unchanged          (Review Focus 4)
# (commit work.txt, head=HEAD)
# --complete 3 "review clean" --start 3 -> rc == 3; task-3-base absent          (Review Focus 5)
# --complete 1 "review clean" --start 2 -> out has "ledger: Task 1: complete (commits ${base:0:7}..${head:0:7}, review clean)",
#                                          "brief: .../task-2-brief.md", "base: $head"; progress.md has the same Task 1 line
# --complete 2 "2 parked"            -> progress.md has "Task 2: complete (commits ${head:0:7}..${head:0:7}, 2 parked)"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `bash tests/claude-code/test-sdd-task-next.sh`
Expected: FAIL (the script does not exist, so the first assertion fails).

- [ ] **Step 3: Implement `skills/subagent-driven-development/scripts/task-next`**

Follow `task-done`'s structure: `set -euo pipefail`, a header comment with usage and exit codes, parse flags in one loop, validate everything (RESULT matches `^(review clean|[0-9]+ parked)$`) before touching anything, then do the `--complete` half, then the `--start` half. Resolve the workspace with `"${BASH:-bash}" "$dir/sdd-workspace" "$plan"` and extract the brief path from `task-brief`'s output with the same `sed` as `executing-plans/scripts/task-start`. Check that the task exists (run `task-brief` and let its exit 3 stop the script) before writing `task-N-base`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `bash tests/claude-code/test-sdd-task-next.sh && bash tests/claude-code/test-executing-plans-scripts.sh && bash tests/claude-code/test-sdd-workspace.sh`
Expected: each prints `PASS`.

- [ ] **Step 5: Document and commit**

Add to `docs/testing.md`: `tests/claude-code/test-sdd-task-next.sh` — bash tests for SDD's `task-next` bookkeeping script.

```bash
git add skills/subagent-driven-development/scripts/task-next tests/claude-code/test-sdd-task-next.sh docs/testing.md
git commit -m "feat: add task-next, one bookkeeping call per SDD task boundary"
```

### Task 2: Wire `task-next` into the SDD task loop

**Files:**
- Modify: `skills/subagent-driven-development/SKILL.md:199-205` (BASE and task-brief), `:241` and `:265` (BASE wording), `:305-312` (completion line)

**Interfaces:**
- Consumes: `task-next` flags and output lines from Task 1.
- Produces: the controller instructions that call it. `task-brief` and `review-package` stay as scripts; `task-brief` is now called only by `task-next`.

- [ ] **Step 1: Rewrite "1. Dispatch the implementer"**

Replace the "Record BASE (`git rev-parse HEAD`)…" paragraph and the **Task brief** bullet's script instruction with one instruction: run `bash scripts/task-next PLAN_FILE --start N`; it prints the brief path and BASE, so record BASE from its output. Keep the five-point dispatch content list unchanged; Task 3 shortens it.

- [ ] **Step 2: Rewrite "5. Complete the task"**

Replace "append the completion line to the ledger in the same message as your other bookkeeping" and the two hand-written line formats with: run `bash scripts/task-next PLAN_FILE --complete N "review clean"` (or `"<K> parked"` after a tripped breaker), and when another task remains add `--start N+1` to the same call. Keep the sentence forbidding moving on with open Critical/Important issues.

- [ ] **Step 3: Check the wording**

Run: `grep -n "task-next" skills/subagent-driven-development/SKILL.md`
Expected: matches in the dispatch section and in "Complete the task".
Run: `grep -n "git rev-parse HEAD\|bash scripts/task-brief" skills/subagent-driven-development/SKILL.md skills/subagent-driven-development/task-reviewer-prompt.md`
Expected: no match in `SKILL.md`. Update the `[BRIEF_FILE]` line in `task-reviewer-prompt.md:192` to say the brief path comes from `task-next --start`.

- [ ] **Step 4: Eval gate**

`evals/` is not cloned in this checkout (`evals/README.md` has the setup). Run the SDD scenarios there and record the results in the commit message or PR notes. If they cannot run, stop and tell your human partner; do not mark this task done.

- [ ] **Step 5: Commit**

```bash
git add skills/subagent-driven-development/SKILL.md skills/subagent-driven-development/task-reviewer-prompt.md
git commit -m "feat: SDD task loop calls task-next at each task boundary"
```

---

## Milestone 2: Smaller prompts

### Task 3: Dispatch by reference

**Files:**
- Modify: `skills/subagent-driven-development/implementer-prompt.md` (preamble above the fence)
- Modify: `skills/subagent-driven-development/task-reviewer-prompt.md` (preamble above the fence)
- Modify: `skills/subagent-driven-development/SKILL.md:206-235` and `:262-292` (dispatch instructions)

**Interfaces:**
- Consumes: the placeholders the templates already define (`[BRIEF_FILE]`, `[REPORT_FILE]`, `[DIFF_FILE]`, `[BASE_SHA]`, `[HEAD_SHA]`, `[GLOBAL_CONSTRAINTS]`, `[directory]`).
- Produces: two fixed dispatch forms the controller writes instead of the filled-in template:
  - Implementer: `Read <skill dir>/implementer-prompt.md, then your brief at <path>. Report to <path>. Work from <dir>. You never dispatch subagents. Deltas: <3–5 lines>.`
  - Reviewer: `Read <skill dir>/task-reviewer-prompt.md. BRIEF_FILE=<path> REPORT_FILE=<path> DIFF_FILE=<path> BASE_SHA=<sha> HEAD_SHA=<sha>. GLOBAL_CONSTRAINTS: <verbatim lines>.`
  - `<skill dir>` is the absolute base directory the controller was given when it loaded the skill. The `model` and `description` stay as parameters of the dispatch tool call, never in the prompt text.

- [ ] **Step 1: Add the "dispatched by reference" preamble to both templates**

Above each fenced block, add a short paragraph: if your dispatch told you to read this file, the `prompt:` block below is your instructions; ignore the `Subagent`, `description:` and `model:` lines (they are for the controller); fill each `[PLACEHOLDER]` from your dispatch message. For the implementer, say that `[Scene-setting]` is the dispatch's Deltas and that Task N and the task name come from the brief's heading.

- [ ] **Step 2: Rewrite the SKILL.md dispatch instructions**

In "1. Dispatch the implementer" replace the five-point content list with the implementer form above: Deltas carry (1) where the task fits, (3) interfaces from earlier tasks, (4) rulings on ambiguity; the brief and report paths are in the form itself. Keep the "no pasted prior-task history" and "no subagents contract" bullets. In "3. Review the task" make the same change for the reviewer form, keeping the rules about copying constraints verbatim and not pre-judging findings.

- [ ] **Step 3: Check the wording**

Run: `grep -c "dispatched by reference\|Dispatched by reference" skills/subagent-driven-development/implementer-prompt.md skills/subagent-driven-development/task-reviewer-prompt.md`
Expected: `1` for each file.
Run: `grep -n "Read <skill dir>" skills/subagent-driven-development/SKILL.md`
Expected: one match for each form.

- [ ] **Step 4: Eval gate**

Run the SDD scenarios in `evals/` that check that implementers spawn no subagents and follow the report contract (see Task 2, Step 4 for setup). Record the results. A failure on either check means the preamble or the form needs rework before this task counts as done.

- [ ] **Step 5: Commit**

```bash
git add skills/subagent-driven-development/implementer-prompt.md skills/subagent-driven-development/task-reviewer-prompt.md skills/subagent-driven-development/SKILL.md
git commit -m "feat: SDD dispatches point subagents at the templates instead of restating them"
```

### Task 4: Builder check only for multi-component specs

**Files:**
- Modify: `skills/brainstorming/SKILL.md:228-245` (the "Builder check" paragraph)

**Interfaces:**
- Consumes: the existing "Size the Work" table (small change vs project).
- Produces: a condition on the builder check inside the "project" case.

- [ ] **Step 1: Change the condition**

Change the paragraph's lead from `**Builder check** (for a project):` to dispatch the subagent when the design has more than one component, or new interfaces other people depend on. Otherwise read the document as that builder yourself, which is what the paragraph already says to do without a subagent tool. Move that final sentence so it covers both cases. Leave the three-pile sorting and the round-of-questions rules as they are.

- [ ] **Step 2: Check the wording**

Run: `grep -n "more than one component\|read the document as that builder" skills/brainstorming/SKILL.md`
Expected: both phrases match, within the builder-check paragraph.

- [ ] **Step 3: Eval gate**

Run the brainstorming scenarios in `evals/` that check spec quality, plus one single-entity CRUD brainstorm, and confirm that no builder-check subagent is dispatched for it. Record the results.

- [ ] **Step 4: Commit**

```bash
git add skills/brainstorming/SKILL.md
git commit -m "feat: brainstorming dispatches the builder check only for multi-component designs"
```

---

## Milestone 3: Docs and rename

### Task 5: Update the docs and rename the product in prose

**Files:**
- Modify: `README.md` (outside the Commercial Services, Installation, Community, Updating and License sections)
- Modify: `AGENTS.md`
- Modify: `docs/testing.md`

**Interfaces:**
- Consumes: the rename rule in Global Constraints; the `docs/testing.md` bullet Task 1 added.
- Produces: docs where the product is called Budgetpowers in prose. Task 6 lists what was left.

- [ ] **Step 1: Confirm the docs need no factual change from Tasks 1–4**

Run: `grep -n -i "ledger\|task-brief\|task-next\|builder check\|builder-check" README.md AGENTS.md`
Expected: no output. If anything matches, update that sentence to match Tasks 1–4 before renaming.

- [ ] **Step 2: Rename the product in prose**

In the three files, change the capitalised product name "Superpowers" to "Budgetpowers" wherever it is prose, including the `# Superpowers` title of `README.md` and "Superpowers — Contributor Guidelines" in `AGENTS.md`. Do not touch: anything in a code span or code block, URLs, `superpowers:` ids, `SUPERPOWERS_ROOT`, the `[superpowers-evals]` link, or the README sections named above.

- [ ] **Step 3: Check the result**

Run: `grep -n "Superpowers" AGENTS.md docs/testing.md`
Expected: only lines where the word sits inside a link target or code span.
Run: `grep -n "Superpowers" README.md`
Expected: every remaining match falls in line range of the five skipped sections (`grep -n '^## ' README.md` gives their bounds).

- [ ] **Step 4: Commit**

```bash
git add README.md AGENTS.md docs/testing.md
git commit -m "docs: call the product Budgetpowers in prose"
```

### Task 6: Identifier cleanup checklist

**Files:**
- Create: `docs/budgetpowers-rename-cleanup.md`

**Interfaces:**
- Consumes: the repo as it stands after Task 5.
- Produces: a checklist a later session can work through; nothing in it is executed here.

- [ ] **Step 1: Take the inventory**

Run: `grep -rIl -i superpowers --exclude-dir=.git --exclude-dir=.bare --exclude-dir=node_modules --exclude-dir=scratch . | sort`
Expected: the list of files that still mention it (about 157 before Task 5).
Also run `find . -iname '*superpowers*' -not -path './.git/*' -not -path './.bare/*' -not -path './node_modules/*'` for file and directory names.

- [ ] **Step 2: Write `docs/budgetpowers-rename-cleanup.md`**

One section per identifier class, each with a file count from the inventory, the files, the replacement to use, and what breaks if the rename is half done. Classes: skill ids and skill directory names (`using-superpowers`, `diagnosing-superpowers`, `auditing-superpowers`, `customizing-superpowers`, `superpowers:*` references); workspace and docs paths (`.superpowers/`, `docs/superpowers/`); `SUPERPOWERS_ROOT` and other env vars; plugin and marketplace manifests and ids; install commands and upstream URLs (these stay upstream's unless the fork publishes its own). End with a suggested order: the manifests and skill ids last, since a half-renamed skill id stops the bootstrap from loading.

- [ ] **Step 3: Commit**

```bash
git add docs/budgetpowers-rename-cleanup.md
git commit -m "docs: checklist for renaming Superpowers identifiers to Budgetpowers"
```
