# Choosing the Reviewer for a Final Review

Used only by the final whole-branch review (executing-plans § Final Review and
subagent-driven-development's final-review.md). Per-task reviews always use
[code-reviewer.md](code-reviewer.md): they run many times, and a deep review
skill there costs too much.

## Tiers

A review skill is one whose description says it reviews code, a diff, or a PR.
Exclude `budgetpowers:*` (tier 5 covers it) and `receiving-code-review`
(it handles feedback, it doesn't produce it).

| Tier | Where |
|------|-------|
| 1 | Deepest review skill in `<repo>/.claude/skills` or `<repo>/.agents/skills` |
| 2 | Any other project-level review skill |
| 3 | Deepest in `~/.claude/skills`, `~/.agents/skills`, or an installed plugin |
| 4 | Any other user-level review skill |
| 5 | `budgetpowers:requesting-code-review` → `code-reviewer.md` |

"Project" means skills in the checkout, not skills in the branch diff. Plugin
skills count as user level.

## Pick

Read only each candidate's description first. Read a body only to rank within a
tier. Take the deepest skill in the highest non-empty tier: the one with the
most distinct review passes or dimensions, by your judgment of its description
and body, not its size.

Write one ledger line:

- `Final: reviewer: <skill> (<tier>) — <why deepest>`
- `Final: reviewer: code-reviewer.md (no review skill found)` when nothing is found

## Dispatch

Unchanged: the most capable model, named explicitly, and the same inputs
(review-package path, plan and spec paths, Review Focus, `Ruling:` pointer). The
prompt tells the reviewer to invoke the chosen skill on the package's range
(base and head SHAs, not a PR number), then return findings as Critical /
Important / Minor plus "Declined to judge", the output contract in
code-reviewer.md. The skill's own format doesn't matter; you re-grade by effect.

Report to the console. Never pass `--comment`, `--fix`, or anything that posts
to a PR or edits the tree.

## Failure

If the chosen skill fails to load or errors, ledger it loudly
(`Final: reviewer: <skill> failed — <error>`) and take the next candidate in the
tier order above. Never swallow the error and never skip the review.
