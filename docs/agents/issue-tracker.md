# Issue tracker

Issues for this repo live in **GitHub Issues** on `JasonRandazza/OhYesMLX`.

Use the `gh` CLI:

- Create: `gh issue create --title "..." --body "..." --label "..."`
- List the frontier: `gh issue list --label ready-for-agent --state open`
- Read one: `gh issue view <n> --comments`
- Close: `gh issue close <n> --comment "..."`

Blocking edges use GitHub's native sub-issue / task-list relationship where available;
otherwise a ticket body carries a `Blocked by: #n, #m` line.

**PRs as a request surface:** off. External pull requests do not enter the triage queue.

## Relationship to PAUL

PAUL owns the loop and the state; GitHub owns the work items. A PAUL plan under
`.paul/phases/` may reference the issues it closes, but `.paul/STATE.md` remains the only
place that records where the project *is*. Do not mirror phase status into issue labels.
