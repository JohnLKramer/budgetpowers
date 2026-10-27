#!/usr/bin/env bash
# Tests for SDD's bookkeeping helper: scripts/task-next closes one task and
# opens the next in a single call -- ledger line for the finished task, then
# the next task's brief path and BASE -- and fails loudly instead of writing
# a ledger line or BASE it cannot stand behind.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SDD_SCRIPTS="$REPO_ROOT/skills/subagent-driven-development/scripts"

FAILURES=0
TEST_ROOT=""

pass() { echo "  [PASS] $1"; }
fail() {
    echo "  [FAIL] $1"
    FAILURES=$((FAILURES + 1))
}

cleanup() {
    if [[ -n "$TEST_ROOT" && -d "$TEST_ROOT" ]]; then
        rm -rf "$TEST_ROOT"
    fi
}

main() {
    echo "=== Test: sdd task-next ==="

    TEST_ROOT="$(mktemp -d)"
    trap cleanup EXIT

    git init -q -b main "$TEST_ROOT/repo"
    local repo
    repo="$(cd "$TEST_ROOT/repo" && git rev-parse --show-toplevel)"
    # Same spelling as the scripts print (pwd), not rev-parse's C:/... on Git Bash.
    repo="$(cd "$repo" && pwd)"
    local git_id=(-c user.email=t@example.com -c user.name=t -c commit.gpgsign=false)

    cat > "$repo/plan.md" <<'PLAN'
# Plan

## Task 1: First thing

Do the first thing.

## Task 2: Second thing

Do the second thing.

## Task 3: Third thing

Do the third thing.
PLAN
    ( cd "$repo" && git add plan.md && git "${git_id[@]}" commit -qm fixture )
    local base
    base="$(cd "$repo" && git rev-parse HEAD)"
    local ws="$repo/.superpowers/sdd/plan"
    local ledger="$ws/progress.md"

    local rc out

    # --- usage errors ---
    rc=0
    (cd "$repo" && "$SDD_SCRIPTS/task-next" plan.md >/dev/null 2>&1) || rc=$?
    if [[ "$rc" -eq 2 ]]; then
        pass "no flags exits 2"
    else
        fail "no flags exits 2 (got $rc)"
    fi
    rc=0
    (cd "$repo" && "$SDD_SCRIPTS/task-next" plan.md --bogus >/dev/null 2>&1) || rc=$?
    if [[ "$rc" -eq 2 ]]; then
        pass "unknown flag exits 2"
    else
        fail "unknown flag exits 2 (got $rc)"
    fi

    # --- a RESULT outside the two SDD forms is rejected ---
    rc=0
    (cd "$repo" && "$SDD_SCRIPTS/task-next" plan.md --complete 1 "done" >/dev/null 2>&1) || rc=$?
    if [[ "$rc" -eq 2 ]] && ! grep -qs "Task 1:" "$ledger"; then
        pass "a RESULT that is neither 'review clean' nor '<K> parked' exits 2 and records nothing"
    else
        fail "a RESULT that is neither 'review clean' nor '<K> parked' exits 2 and records nothing (rc=$rc)"
    fi

    # --- completing a task whose BASE was never recorded fails loudly ---
    rc=0
    (cd "$repo" && "$SDD_SCRIPTS/task-next" plan.md --complete 1 "review clean" >/dev/null 2>&1) || rc=$?
    if [[ "$rc" -eq 3 ]] && ! grep -qs "Task 1:" "$ledger"; then
        pass "--complete without a recorded BASE exits 3 and records nothing"
    else
        fail "--complete without a recorded BASE exits 3 and records nothing (rc=$rc)"
    fi

    # The message must not send the controller to --start: after the task's
    # commits exist that would record today's HEAD and leave an empty range.
    local err
    err="$(cd "$repo" && "$SDD_SCRIPTS/task-next" plan.md --complete 1 "review clean" 2>&1 >/dev/null)" || true
    if [[ "$err" == *"$ws/task-1-base"* && "$err" != *"run --start"* ]]; then
        pass "the missing-BASE message names the BASE file and does not suggest --start"
    else
        fail "the missing-BASE message names the BASE file and does not suggest --start"
        echo "    got: $err"
    fi

    # --- starting a task that is not in the plan ---
    rc=0
    (cd "$repo" && "$SDD_SCRIPTS/task-next" plan.md --start 9 >/dev/null 2>&1) || rc=$?
    if [[ "$rc" -eq 3 && ! -e "$ws/task-9-base" ]]; then
        pass "--start for a task not in the plan exits 3 and leaves no BASE file"
    else
        fail "--start for a task not in the plan exits 3 and leaves no BASE file (rc=$rc)"
    fi

    # --- --start: brief path and BASE in one call ---
    out="$(cd "$repo" && "$SDD_SCRIPTS/task-next" plan.md --start 1)"
    if [[ "$out" == *"brief: $ws/task-1-brief.md"* && "$out" == *"base: $base"* ]]; then
        pass "--start prints the brief path and BASE"
    else
        fail "--start prints the brief path and BASE"
        echo "    got: $out"
    fi
    if [[ "$(cat "$ws/task-1-base" 2>/dev/null)" == "$base" ]]; then
        pass "--start stores BASE in the workspace"
    else
        fail "--start stores BASE in the workspace"
    fi

    # --- starting the same task twice would move BASE; refuse ---
    ( cd "$repo" && echo x > work.txt && git add work.txt && git "${git_id[@]}" commit -qm "task 1" )
    local head
    head="$(cd "$repo" && git rev-parse HEAD)"
    rc=0
    (cd "$repo" && "$SDD_SCRIPTS/task-next" plan.md --start 1 >/dev/null 2>&1) || rc=$?
    if [[ "$rc" -eq 4 && "$(cat "$ws/task-1-base")" == "$base" ]]; then
        pass "--start for an already started task exits 4 and keeps the recorded BASE"
    else
        fail "--start for an already started task exits 4 and keeps the recorded BASE (rc=$rc)"
    fi

    # --- a failing --complete must not start the next task ---
    rc=0
    (cd "$repo" && "$SDD_SCRIPTS/task-next" plan.md --complete 3 "review clean" --start 3 >/dev/null 2>&1) || rc=$?
    if [[ "$rc" -eq 3 && ! -e "$ws/task-3-base" ]]; then
        pass "a failing --complete does not start the next task"
    else
        fail "a failing --complete does not start the next task (rc=$rc)"
    fi

    # --- close one task and open the next in one call ---
    out="$(cd "$repo" && "$SDD_SCRIPTS/task-next" plan.md --complete 1 "review clean" --start 2)"
    local expected="Task 1: complete (commits ${base:0:7}..${head:0:7}, review clean)"
    if [[ "$out" == *"ledger: $expected"* && "$out" == *"brief: $ws/task-2-brief.md"* && "$out" == *"base: $head"* ]]; then
        pass "--complete plus --start prints the ledger line, the next brief and BASE"
    else
        fail "--complete plus --start prints the ledger line, the next brief and BASE"
        echo "    got: $out"
    fi
    if grep -qF "$expected" "$ledger"; then
        pass "--complete appends the completion line to the ledger"
    else
        fail "--complete appends the completion line to the ledger"
        echo "    ledger:"; sed 's/^/      /' "$ledger" 2>/dev/null || echo "      (missing)"
    fi

    # --- a parked result is accepted ---
    (cd "$repo" && "$SDD_SCRIPTS/task-next" plan.md --complete 2 "2 parked" >/dev/null)
    if grep -qF "Task 2: complete (commits ${head:0:7}..${head:0:7}, 2 parked)" "$ledger"; then
        pass "--complete accepts '<K> parked'"
    else
        fail "--complete accepts '<K> parked'"
    fi

    echo
    if [[ "$FAILURES" -eq 0 ]]; then
        echo "PASS"
    else
        echo "FAIL ($FAILURES)"
        exit 1
    fi
}

main "$@"
