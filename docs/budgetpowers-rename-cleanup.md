# Renaming Superpowers identifiers to Budgetpowers

The prose rename is done: the product name reads "Budgetpowers" in `README.md`, `AGENTS.md` and `docs/testing.md`. This file lists what is left. Nothing here has been renamed.

Counts are files that mention the string, taken on 2026-10-27 with:

```bash
EX="--exclude-dir=.git --exclude-dir=.bare --exclude-dir=node_modules --exclude-dir=scratch --exclude-dir=.superpowers"
grep -rIl -i superpowers $EX . | wc -l                     # 158 files in all
grep -rIl -e '<string>' $EX . | wc -l                      # per class below
find . -iname '*superpowers*' -not -path './.git/*' -not -path './.bare/*' -not -path './node_modules/*' -not -path './scratch/*' -not -path './.superpowers/*'
```

Classes overlap, so the counts do not add up to 158. The replacement names are proposals: lowercase `budgetpowers` everywhere.

## 1. Skill ids and skill directories

| String | Files | Proposed |
|---|---|---|
| `superpowers:<skill>` references | 53 | `budgetpowers:<skill>` |
| `using-superpowers` | 42 | `using-budgetpowers` |
| `diagnosing-superpowers` | 11 | `diagnosing-budgetpowers` |
| `auditing-superpowers`, `customizing-superpowers` | 1 each | rename with the others; these two skills live outside this tree |

Directories to move: `skills/using-superpowers/`, `skills/diagnosing-superpowers/`, `tests/diagnosing-superpowers/`.

**If done halfway:** the session-start bootstrap loads `using-superpowers` by name. A half-renamed id stops skills from auto-triggering, and nothing says so. Rename the directory, the bootstrap hooks and the manifests in one change.

- [ ] done

## 2. Workspace and docs paths

| String | Files | Proposed |
|---|---|---|
| `.superpowers/` (the SDD workspace, written by `sdd-workspace` and read by the SDD and executing-plans scripts) | 24 | `.budgetpowers/` |
| `docs/superpowers/` (where skills say specs and plans go) | 27 | `docs/budgetpowers/` |

**If done halfway:** a run in flight keeps its ledger under the old directory and the renamed scripts will not find it, so the resume check starts the plan again. Rename between runs. Existing specs and plans move with `git mv`.

- [ ] done

## 3. Environment variables

`SUPERPOWERS_` appears in 14 files (`SUPERPOWERS_ROOT`, `SUPERPOWERS_DISABLE_TELEMETRY`, and any others the grep turns up). Proposed: `BUDGETPOWERS_`.

**If done halfway:** a user whose shell sets the old name has it ignored without a message. This repo's rule is to fail loudly rather than add a silent fallback, so decide whether the old name should error or just be dropped from the docs.

- [ ] done

## 4. Entry-point file names

`.opencode/plugins/superpowers.js`, `.pi/extensions/superpowers.ts`, `assets/superpowers-small.svg`. The manifests and `tests/opencode/test-plugin-loading.sh` name these files.

**If done halfway:** the harness loads nothing from the old path.

- [ ] done

## 5. Plugin and marketplace manifests

`.agents/plugins/marketplace.json`, `.antigravity-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`, `.cursor-plugin/plugin.json`, `.devin-plugin/plugin.json`, `.hermes-plugin/__init__.py`, `.hermes-plugin/plugin.yaml`, `.kimi-plugin/plugin.json`, `.muse-plugin/marketplace.json`, `.muse-plugin/plugin.json`, `gemini-extension.json`, `package.json`, plus `scripts/package-codex-plugin.sh` and `scripts/sync-to-codex-plugin.sh`. Install ids of the form `superpowers@<marketplace>` appear in 5 files.

The tests that read them: `tests/antigravity/`, `tests/codex/`, `tests/codex-plugin-sync/`, `tests/devin/`, `tests/hermes/`, `tests/kimi/`, `tests/opencode/`.

**If done halfway:** a manifest that names a skill or entry point that no longer exists fails at install time, and the manifest tests fail first.

- [ ] done

## 6. Upstream URLs and install commands: leave alone

| String | Files |
|---|---|
| `obra/superpowers` | 24 |
| `superpowers-marketplace` | 3 |
| `superpowers-evals` (the eval lab clone) | 7 |
| `primeradiant`, `prime-radiant` | 8 |

These point at upstream's repositories, marketplaces and support address. This fork's remote is `JohnLKramer/budgetpowers`. Change one only if the fork publishes its own replacement, and change it to that replacement, not to a guess.

## 7. Prose left on purpose

In `README.md`: the Commercial Services, Installation, Community, Updating and License sections, and the "Visual companion telemetry" paragraph. All of them describe upstream's support, distribution or telemetry. Lowercase prose such as "figure out what went wrong with superpowers in this session" is the trigger phrase for a skill and moves with class 1.

## Suggested order

1. Decide class 6 (nothing to do unless the fork publishes its own).
2. Class 2, between runs, with `git mv`.
3. Class 3, once the error-or-drop decision is made.
4. Class 4.
5. Classes 1 and 5 together, last, as one change, so the bootstrap and the manifests never disagree. Run every manifest test in `tests/` before committing.
6. Re-run the grep above. What remains should be class 6 and class 7.
