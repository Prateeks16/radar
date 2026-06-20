---
name: radar
description: Show a developer their open work across every GitHub repo, from the terminal - open PRs they authored, PRs awaiting their review, and issues assigned to them, with a stale flag for anything gone quiet. Also a `log` view of merged/closed history and an ASCII shareable recap card. No dashboard, no signup; uses the existing `gh` login. Trigger when the user asks what they're working on, what's open, what needs review, their PR/issue status, their merge history, or invokes /radar.
---

# radar

Your open work across every repo, in the terminal. No dashboard, no signup.

`radar` answers a question no GitHub leaderboard or notifications page answers cleanly:
**what work do I have in flight right now, scattered across all my repos?** It reads
the already-authenticated `gh` CLI - there is no separate token or account to set up.

## Commands

Run the bundled script with the project Python:

```bash
python "<skill_dir>/scripts/radar.py" <command> [args]
```

| Command | What it does |
|---|---|
| `wip` (default) | Live snapshot of work in flight, in 5 sections: **MERGED (last 7d)**, **PR CONFLICTS** (open PRs needing a rebase), **PR IN REVIEW** (your other open PRs, tagged with their review decision), **ASSIGNED, NO PR YET** (issues on you with no linked PR), and **AWAITING YOUR REVIEW** (PRs others want you to review). Anything idle past `stale_days` (default 14) is flagged `[STALE Nd]`. The daily-driver view. |
| `log [--since YYYY-MM-DD]` | Merged/closed history since a date (default: 30 days ago, UTC). Upserts into a local log keyed by URL - idempotent, safe to re-run. Writes `log.json` + `log.md`. |
| `log --recap` | An ASCII shareable card summarising the logged history (PRs merged, repos touched, date range, most-merged repos). ASCII-safe for any terminal. |

### Typical usage

- "What am I working on?" / "What's open?" -> `python .../radar.py wip`
- "Anything waiting on my review?" -> `python .../radar.py wip` (see the AWAITING YOUR REVIEW section)
- "What did I merge lately?" -> `python .../radar.py log`
- "Show my work since May" -> `python .../radar.py log --since 2026-05-01`
- "Give me a card to share" -> `python .../radar.py log --recap`

## Behaviour notes

1. **Auth is `gh`-only.** The script uses your existing `gh auth login`. If `gh` is
   missing or unauthenticated it fails loud with a one-line fix and does nothing else.
2. **All day boundaries are UTC.** GitHub's search index is UTC, so `radar` anchors
   every date to UTC and prints `day=UTC` in the header to make that explicit. Don't
   "correct" dates to local time - that reintroduces off-by-one bugs.
3. **`wip` is a live view** - it holds no state and writes nothing. `log` is the only
   command that persists, into `~/.claude/radar/`.
4. **Run `log` before `log --recap`** - the recap summarises whatever is already in the
   local log; it does not fetch.
5. **Output is ASCII-only** by design (titles are coerced) so Windows consoles and pipes
   never mangle it. After running, give the user a short natural-language read of the
   result, not just the raw table.
6. **Config** lives at `~/.claude/radar/config.json`; the only knob is `stale_days`.

## Known limits

- `wip` surfaces only what the `gh` token can see - private/org repos outside its scope
  won't appear, and review-requested/assigned items depend on token visibility.
- "PR IN REVIEW" lists every open authored PR that is not conflicting; "no reviewers"
  means none are requested yet, not that the PR is unreviewable.
- "ASSIGNED, NO PR YET" detects a linked PR via the issue's connected / cross-referenced
  timeline events - a PR linked only by free-text mention may not be detected.
- GitHub's search index lags reality by up to a minute or two; a just-opened PR may not
  show immediately.
- Authored PRs only for the "YOUR OPEN PRs" section (co-authored-but-not-authored PRs
  won't list there).
