#!/usr/bin/env python3
"""radar - your open work across every repo, in the terminal.

Two views, both powered by the authenticated `gh` CLI (no separate token):

  radar wip            live snapshot of work in flight - open PRs you authored,
                       PRs waiting on your review, issues assigned to you, with
                       a STALE flag for anything gone quiet.
  radar log [--since]  history of merged/closed work, upserted into a local log.
  radar log --recap    an ASCII shareable card summarising that history.

All GitHub day boundaries are UTC (GitHub's search index is UTC); the output
says so. No third-party deps - standard library only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HOME = Path(os.path.expanduser("~"))
DATA_DIR = HOME / ".claude" / "radar"
LOG_JSON = DATA_DIR / "log.json"
LOG_MD = DATA_DIR / "log.md"
CONFIG = DATA_DIR / "config.json"

DEFAULT_CONFIG = {
    "_comment": "stale_days: a PR/issue is flagged STALE when it has not been "
                "updated in this many days. Tune to taste.",
    "stale_days": 14,
}


# ---------------------------------------------------------------------------
# gh / GitHub helpers
# ---------------------------------------------------------------------------
def _have_gh() -> bool:
    return shutil.which("gh") is not None


def _fail_auth() -> None:
    sys.exit(
        "radar: GitHub CLI not ready.\n"
        "  Fix: install gh (https://cli.github.com) then run `gh auth login`.\n"
        "  radar uses your existing gh login - no separate token to manage."
    )


def gh_api(path: str, params: list[str] | None = None, graphql: bool = False) -> dict:
    """Call the GitHub API through `gh api`. Returns parsed JSON."""
    if not _have_gh():
        _fail_auth()
    if graphql:
        cmd = ["gh", "api", "graphql"]
    else:
        cmd = ["gh", "api"]
        if params:
            cmd += ["-X", "GET"]
        cmd.append(path)
    for p in params or []:
        cmd += ["-f", p] if not graphql else ["-F", p]
    # gh emits UTF-8; force it so Windows' default cp1252 doesn't choke on
    # non-ASCII titles. errors="replace" keeps a stray byte from killing a fetch.
    res = subprocess.run(cmd, capture_output=True, text=True,
                         encoding="utf-8", errors="replace", env=dict(os.environ))
    if res.returncode != 0:
        err = res.stderr.strip()
        if "authentication" in err.lower() or "gh auth login" in err.lower():
            _fail_auth()
        sys.exit(f"radar: gh api failed ({path or 'graphql'}):\n{err}")
    try:
        return json.loads(res.stdout or "{}")
    except json.JSONDecodeError:
        sys.exit(f"radar: could not parse gh output for {path}:\n{res.stdout[:500]}")


def whoami() -> str:
    return gh_api("user")["login"]


def search_issues(q: str) -> list[dict]:
    """Paginated search/issues query (capped at 1000 results)."""
    items: list[dict] = []
    page = 1
    while True:
        data = gh_api("search/issues", params=[f"q={q}", "per_page=100", f"page={page}"])
        batch = data.get("items", [])
        items.extend(batch)
        if len(batch) < 100 or page >= 10:
            break
        page += 1
    return items


# ---------------------------------------------------------------------------
# config + log
# ---------------------------------------------------------------------------
def load_config() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG.exists():
        CONFIG.write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding="utf-8")
    cfg = dict(DEFAULT_CONFIG)
    try:
        cfg.update(json.loads(CONFIG.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):
        pass
    return cfg


def load_log() -> dict:
    if LOG_JSON.exists():
        try:
            return json.loads(LOG_JSON.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"entries": {}}  # keyed by html_url


def save_log(log: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_JSON.write_text(json.dumps(log, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# time helpers (everything UTC)
# ---------------------------------------------------------------------------
def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def parse_iso(ts: str | None) -> dt.datetime | None:
    if not ts:
        return None
    try:
        return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def age_days(ts: str | None) -> int | None:
    d = parse_iso(ts)
    if d is None:
        return None
    return (now_utc() - d).days


def utc_day(ts: str | None) -> str:
    d = parse_iso(ts)
    return d.date().isoformat() if d else "?"


def repo_from_item(item: dict) -> str:
    return item.get("repository_url", "").replace("https://api.github.com/repos/", "")


def ascii_safe(s: str) -> str:
    """Drop to ASCII for console output - Windows terminals mangle Unicode."""
    return (s or "").encode("ascii", "replace").decode("ascii")


# ---------------------------------------------------------------------------
# wip - live snapshot
# ---------------------------------------------------------------------------
def cmd_wip(args: argparse.Namespace) -> None:
    cfg = load_config()
    stale_days = int(cfg.get("stale_days", 14))
    login = whoami()

    my_prs = search_issues("author:@me type:pr state:open")
    review = search_issues("review-requested:@me type:pr state:open")
    assigned = search_issues("assignee:@me type:issue state:open")

    print(f"\nradar wip - @{login}  (day=UTC, as of {now_utc():%Y-%m-%d %H:%M}Z)")
    print("=" * 60)

    _section("YOUR OPEN PRs", my_prs, stale_days)
    _section("AWAITING YOUR REVIEW", review, stale_days)
    _section("ISSUES ASSIGNED TO YOU", assigned, stale_days)

    total = len(my_prs) + len(review) + len(assigned)
    stale = sum(1 for it in my_prs + review + assigned
                if (age_days(it.get("updated_at")) or 0) >= stale_days)
    print("-" * 60)
    tail = f", {stale} stale (>{stale_days}d)" if stale else ""
    print(f"{total} items in flight: {len(my_prs)} PRs, "
          f"{len(review)} to review, {len(assigned)} issues{tail}.\n")


def _section(label: str, items: list[dict], stale_days: int) -> None:
    print(f"\n{label}  ({len(items)})")
    if not items:
        print("  (none)")
        return
    items = sorted(items, key=lambda it: it.get("updated_at") or "", reverse=True)
    for it in items:
        repo = repo_from_item(it)
        num = it.get("number", "?")
        age = age_days(it.get("updated_at"))
        flag = f"  [STALE {age}d]" if age is not None and age >= stale_days else ""
        title = ascii_safe((it.get("title") or "").strip())
        if len(title) > 56:
            title = title[:55] + "~"
        print(f"  {repo}#{num}  {title}{flag}")


# ---------------------------------------------------------------------------
# log - merged/closed history
# ---------------------------------------------------------------------------
def _entry_from_item(item: dict, kind: str) -> dict:
    pr = item.get("pull_request") or {}
    if kind == "pr":
        if pr.get("merged_at"):
            status, when = "merged", pr.get("merged_at")
        else:
            status, when = "closed", item.get("closed_at")
    else:
        status, when = "closed", item.get("closed_at")
    return {
        "url": item["html_url"],
        "kind": kind,
        "repo": repo_from_item(item),
        "number": item.get("number"),
        "title": ascii_safe((item.get("title") or "").strip()),
        "status": status,
        "closed_day": utc_day(when),  # UTC
        "created_at": item.get("created_at"),
        "synced_at": now_utc().isoformat(timespec="seconds"),
    }


def cmd_log(args: argparse.Namespace) -> None:
    if args.recap:
        recap()
        return

    since = args.since or (now_utc().date() - dt.timedelta(days=30)).isoformat()
    log = load_log()
    login = whoami()

    merged = search_issues(f"author:@me type:pr is:merged merged:>={since}")
    closed_pr = search_issues(f"author:@me type:pr is:unmerged closed:>={since}")
    closed_iss = search_issues(f"author:@me type:issue is:closed closed:>={since}")

    fresh: list[dict] = []
    for it in merged + closed_pr:
        e = _entry_from_item(it, "pr")
        log["entries"][e["url"]] = e
        fresh.append(e)
    for it in closed_iss:
        e = _entry_from_item(it, "issue")
        log["entries"][e["url"]] = e
        fresh.append(e)

    save_log(log)
    write_markdown(log)
    print_log(log, since, login)


def print_log(log: dict, since: str, login: str) -> None:
    entries = [e for e in log.get("entries", {}).values()
               if e.get("closed_day", "?") >= since]
    print(f"\nradar log - @{login}  (since {since}, day=UTC)")
    print("=" * 60)
    if not entries:
        print("No merged/closed work in this window.\n")
        return

    by_day: dict[str, list[dict]] = {}
    for e in entries:
        by_day.setdefault(e.get("closed_day", "?"), []).append(e)

    for day in sorted(by_day, reverse=True):
        print(f"\n{day}")
        for e in sorted(by_day[day], key=lambda x: x["repo"]):
            badge = "MERGED" if e["status"] == "merged" else "CLOSED"
            print(f"  [{badge}] {e['repo']}#{e['number']}  {e['title']}")

    merged = [e for e in entries if e["status"] == "merged" and e["kind"] == "pr"]
    print("-" * 60)
    print(f"{len(merged)} merged PRs, {len(entries) - len(merged)} other closed, "
          f"across {len({e['repo'] for e in entries})} repos.\n")


def write_markdown(log: dict) -> None:
    entries = sorted(log.get("entries", {}).values(),
                     key=lambda e: (e.get("closed_day", ""), e.get("repo", "")),
                     reverse=True)
    lines = ["# radar log\n",
             f"_Updated: {now_utc().isoformat(timespec='seconds')} (day=UTC)_\n"]
    cur = None
    for e in entries:
        if e.get("closed_day") != cur:
            cur = e.get("closed_day")
            lines.append(f"\n## {cur}\n")
        badge = e["status"].upper()
        lines.append(f"- [{badge}] {e['repo']} - [{e['title']}]({e['url']})")
    LOG_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# log --recap - ASCII shareable card
# ---------------------------------------------------------------------------
def recap() -> None:
    log = load_log()
    entries = list(log.get("entries", {}).values())
    if not entries:
        print("Nothing to recap yet. Run `radar log` first.")
        return

    merged = [e for e in entries if e["status"] == "merged" and e["kind"] == "pr"]
    repos = sorted({e["repo"] for e in entries})
    days = sorted(e["closed_day"] for e in entries if e.get("closed_day", "?") != "?")
    span = f"{days[0]} -> {days[-1]}" if days else "n/a"
    login = whoami()

    top: dict[str, int] = {}
    for e in merged:
        top[e["repo"]] = top.get(e["repo"], 0) + 1
    top_repos = sorted(top.items(), key=lambda kv: kv[1], reverse=True)[:3]

    W = 50
    def row(s: str = "") -> str:
        return "| " + s.ljust(W - 4) + " |"

    print()
    print("+" + "-" * (W - 2) + "+")
    print(row(f"radar recap  @{login}"))
    print(row(f"{span}  (day=UTC)"))
    print("+" + "-" * (W - 2) + "+")
    print(row())
    print(row(f"  {len(merged):>4}  PRs merged"))
    print(row(f"  {len(entries) - len(merged):>4}  other items closed"))
    print(row(f"  {len(repos):>4}  repos touched"))
    print(row())
    if top_repos:
        print(row("  most-merged:"))
        for repo, n in top_repos:
            name = repo if len(repo) <= W - 12 else repo[:W - 13] + "~"
            print(row(f"    {n:>3}x {name}"))
        print(row())
    print(row("  radar - open work in your terminal"))
    print("+" + "-" * (W - 2) + "+")
    print()


# ---------------------------------------------------------------------------
# cli
# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(prog="radar", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("wip", help="live snapshot of work in flight (default)")

    p_log = sub.add_parser("log", help="merged/closed history")
    p_log.add_argument("--since", default=None, help="YYYY-MM-DD (default: 30d ago, UTC)")
    p_log.add_argument("--recap", action="store_true", help="print an ASCII shareable card")

    args = ap.parse_args()
    cmd = args.cmd or "wip"  # wip is the default view
    if cmd == "wip":
        cmd_wip(args)
    elif cmd == "log":
        cmd_log(args)


if __name__ == "__main__":
    main()
