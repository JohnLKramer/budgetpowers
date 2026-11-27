#!/usr/bin/env bash
# Drive one headless budgetpowers build turn by turn, then analyze it.
# total_cost_usd is cumulative across --resume, so each turn gets the full budget and this
# script enforces the cumulative cap itself after every turn.
# Usage: tests/token-baseline/run.sh <crud|gridworld|smoke> [budget_usd]
set -euo pipefail

app=$1
budget=${2:-50}
harness="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$harness/../.." && pwd)"
prompt_file="$harness/prompts/$app.md"
[ -f "$prompt_file" ] || { echo "no prompt for $app: $prompt_file" >&2; exit 2; }

run="$repo/scratch/claude-work/$app-$(date +%Y%m%d-%H%M)"
mkdir -p "$run/app" "$run/turns" "$run/transcripts"
git -C "$run/app" init -q
git -C "$run/app" commit -q --allow-empty -m "empty start"
log="$run/driver.log"

reply='Approved. Choose your recommended option and continue. When the plan asks for an execution method, choose subagent-driven development.'
keep_branch='Keep the branch as-is.'
max_turns=25

# Prints: session_id <TAB> subtype <TAB> total_cost_usd, then the result text on following lines.
result_of() {
  python3 - "$1" <<'EOF'
import json, sys
res = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
res = [r for r in res if r.get("type") == "result"]
if not res:
    sys.exit(f"no result event in {sys.argv[1]}")
r = res[-1]
print(f"{r['session_id']}\t{r['subtype']}\t{r.get('total_cost_usd', 0)}")
print(r.get("result") or "")
EOF
}

stop() {
  echo "stop_reason=$1" >> "$log"
  echo "$app: stopped ($1) after $turn turn(s), \$$spent spent — $run"
}

session=""
spent=0
turn=0
idle=0
message="$(cat "$prompt_file")"
stop_reason=""
while [ -z "$stop_reason" ]; do
  turn=$((turn + 1))
  out="$run/turns/$(printf %02d "$turn").jsonl"
  resume=()
  [ -n "$session" ] && resume=(--resume "$session")
  set +e
  (cd "$run/app" && claude -p "$message" ${resume[@]+"${resume[@]}"} \
      --output-format stream-json --verbose --model claude-opus-5-5 \
      --plugin-dir "$repo" --setting-sources project --strict-mcp-config \
      --settings "$harness/isolation-settings.json" \
      --permission-mode bypassPermissions \
      --max-budget-usd "$budget" < /dev/null > "$out" 2> "$out.stderr")
  rc=$?
  set -e

  parsed="$(result_of "$out")" || { stop_reason="error:no result (exit $rc, see $out.stderr)"; break; }
  IFS=$'\t' read -r sid subtype cost <<< "$(head -1 <<< "$parsed")"
  text="$(tail -n +2 <<< "$parsed")"
  spent=$cost  # total_cost_usd is cumulative across resumes
  echo "turn=$turn session=$sid reply=${message:0:40} result=$subtype cost=$cost" >> "$log"

  if [ -z "$session" ]; then session=$sid; fi
  if [ "$sid" != "$session" ]; then stop_reason="error:resume forked session $session -> $sid"; break; fi
  if [[ "$subtype" == *budget* ]]; then stop_reason="budget"; break; fi
  if [ "$rc" -ne 0 ]; then stop_reason="error:claude exit $rc ($subtype)"; break; fi

  main_jsonl=$(ls ~/.claude/projects/*/"$session.jsonl" 2>/dev/null | head -1 || true)
  finished=no
  if [ -n "$main_jsonl" ] && grep -qE '"skill": ?"budgetpowers:finishing-a-development-branch"' "$main_jsonl"; then finished=yes; fi
  sent="$message"
  message="$reply"
  # A turn that made no tool calls and asked nothing means the agent is waiting with nothing to do.
  if ! grep -q '"type":"tool_use"' "$out" && ! grep -q '?' <<< "$text"; then idle=$((idle + 1)); else idle=0; fi
  if [ "$idle" -ge 2 ]; then stop_reason="done"; break; fi
  if [ "$finished" = yes ]; then
    if grep -qiE 'merge|pull request|\bPR\b' <<< "$text" && [ "$sent" != "$keep_branch" ]; then
      message="$keep_branch"
    elif ! grep -q '?' <<< "$text"; then
      stop_reason="done"; break
    fi
  fi
  if python3 -c "import sys; sys.exit(0 if $budget - $spent <= 0 else 1)"; then stop_reason="budget"; break; fi
  if [ "$turn" -ge "$max_turns" ]; then stop_reason="turn-cap"; break; fi
done
stop "$stop_reason"
[ -n "$session" ] || exit 1

main_jsonl=$(ls ~/.claude/projects/*/"$session.jsonl" | head -1)
cp "$main_jsonl" "$run/transcripts/"
if [ -d "${main_jsonl%.jsonl}/subagents" ]; then
  mkdir -p "$run/transcripts/$session"
  cp -R "${main_jsonl%.jsonl}/subagents" "$run/transcripts/$session/"
fi

# Outcome: run the tests where the build landed (newest non-main worktree, else app/).
where="$run/app"
wts=$(git -C "$run/app" worktree list --porcelain | awk '/^worktree /{w=$2} /^branch /{if ($2 !~ /^refs\/heads\/(main|master)$/) print w}')
if [ "$(grep -c . <<< "$wts")" -gt 1 ]; then echo "more than one build worktree, pick one by hand: $wts" >&2; exit 1; fi
[ -n "$wts" ] && where="$wts"
case "$app" in
  gridworld) cmd="uv run pytest" ;;
  crud) cmd="export JAVA_HOME=\$HOME/.sdkman/candidates/java/current && docker compose up -d && ./gradlew --gradle-user-home /Users/john.kramer/.gradle test" ;;
  smoke) cmd="test -f hello.txt" ;;
esac
if (cd "$where" && bash -c "$cmd") > "$run/outcome.log" 2>&1; then tests=pass; else tests=fail; fi
printf '{"tests": "%s", "command": "%s", "where": "%s"}\n' "$tests" "$cmd" "$where" > "$run/outcome.json"

cd "$harness" && uv run -q --python 3.12 -m analyze "$run"
