#!/usr/bin/env python3
"""
update_language_stats.py
Fetches language statistics from the GitHub API for a given user,
calculates percentages, generates a Markdown table with a visual bar,
and updates the README.md between the LANGUAGE-STATS comment markers.

Usage:
    GITHUB_TOKEN=<token> GITHUB_USERNAME=<username> python3 update_language_stats.py

The workflow runs on Python 3.12; the syntax used here requires Python 3.10+.

No external dependencies — uses only Python standard library.
"""

import json
import os
import sys
import urllib.request
import urllib.error
import urllib.parse

# ── Configuration ────────────────────────────────────────────────────────────
GITHUB_TOKEN    = os.environ.get("GITHUB_TOKEN", "")
GITHUB_USERNAME = os.environ.get("GITHUB_USERNAME", "misterAnt92TV")
README_PATH     = os.environ.get("README_PATH", "README.md")
API_BASE        = "https://api.github.com"

MARKER_START = "<!-- LANGUAGE-STATS:START -->"
MARKER_END   = "<!-- LANGUAGE-STATS:END -->"

BAR_FILLED  = "█"
BAR_EMPTY   = "░"
BAR_LENGTH  = 20
MATERIAL_COLORS = [
    "7E57C2",
    "42A5F5",
    "26A69A",
    "66BB6A",
    "FFA726",
    "EF5350",
    "EC407A",
    "8D6E63",
]


# ── GitHub API helpers ────────────────────────────────────────────────────────
def gh_get(url: str) -> dict | list:
    """
    Perform an authenticated GET request and return the parsed JSON.

    Returns a list for collection endpoints (e.g. /repos) and a dict for
    object endpoints (e.g. /languages). Callers should handle the expected type.
    Raises urllib.error.HTTPError on non-2xx responses.
    """
    req = urllib.request.Request(url)
    req.add_header("Authorization", "Bearer " + GITHUB_TOKEN)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "language-stats-updater/1.0")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def get_all_repos(username: str) -> list:
    """Return all public repositories for a user (handles pagination)."""
    repos = []
    page = 1
    while True:
        url = (
            f"{API_BASE}/users/{username}/repos"
            f"?type=public&per_page=100&page={page}"
        )
        try:
            page_data = gh_get(url)
        except urllib.error.HTTPError as exc:
            print(
                f"ERROR: could not fetch repositories for {username} "
                f"(HTTP {exc.code}: {exc.reason}). "
                "Check that GITHUB_TOKEN is valid and has the correct permissions.",
                file=sys.stderr,
            )
            sys.exit(1)
        if not page_data:
            break
        repos.extend(page_data)
        if len(page_data) < 100:
            break
        page += 1
    return repos


def get_repo_languages(username: str, repo_name: str) -> dict:
    """Return a {language: bytes} dict for a single repository."""
    url = f"{API_BASE}/repos/{username}/{repo_name}/languages"
    try:
        return gh_get(url)
    except urllib.error.HTTPError as exc:
        print(
            f"WARNING: could not fetch languages for {username}/{repo_name} "
            f"(HTTP {exc.code}). Skipping.",
            file=sys.stderr,
        )
        return {}


# ── Stats computation ─────────────────────────────────────────────────────────
def aggregate_languages(username: str) -> dict[str, int]:
    """
    Return a {language: total_bytes} mapping across public repos.

    Forks and archived repos are excluded. Returns {} when none qualify.
    """
    repos = get_all_repos(username)
    totals: dict[str, int] = {}
    for repo in repos:
        if repo.get("fork") or repo.get("archived"):
            continue
        lang_data = get_repo_languages(username, repo["name"])
        for lang, nbytes in lang_data.items():
            totals[lang] = totals.get(lang, 0) + nbytes
    return totals


def compute_percentages(totals: dict) -> list:
    """
    Return a sorted list of (language, percentage) tuples,
    keeping only languages that represent >= 0.5% of total bytes.

    Percentages are rounded to one decimal place, so displayed values
    may not sum to exactly 100 % (typical deviation is < 1 %).
    """
    grand_total = sum(totals.values())
    if grand_total == 0:
        return []
    result = [
        (lang, round(nbytes / grand_total * 100, 1))
        for lang, nbytes in totals.items()
    ]
    result.sort(key=lambda x: x[1], reverse=True)
    return [(lang, pct) for lang, pct in result if pct >= 0.5]


# ── Markdown rendering ────────────────────────────────────────────────────────
def make_bar(pct: float) -> str:
    """Render a fixed-width text bar for a percentage using filled and empty block characters."""
    # Clamp the filled cells to the valid 0..BAR_LENGTH range to guard
    # against unexpected negative values and percentages slightly above 100.
    filled = max(0, min(round(pct / 100 * BAR_LENGTH), BAR_LENGTH))
    return BAR_FILLED * filled + BAR_EMPTY * (BAR_LENGTH - filled)


def make_percentage_badge(pct: float, rank: int) -> str:
    """Render a Material-inspired shields.io badge for a percentage, cycling colors by rank."""
    color = MATERIAL_COLORS[rank % len(MATERIAL_COLORS)]
    query = urllib.parse.urlencode(
        {
            "label": "share",
            "message": f"{pct:.1f}%",
            "color": color,
            "style": "for-the-badge",
            "logo": "materialdesign",
            "logoColor": "white",
        }
    )
    return (
        f"![{pct:.1f}%]"
        f"(https://img.shields.io/static/v1?{query})"
    )


def escape_table_text(text: str) -> str:
    """Escape Markdown-sensitive characters used in README table cells."""
    for old, new in (
        ("\\", "\\\\"),
        ("|", "\\|"),
        ("*", "\\*"),
        ("_", "\\_"),
        ("`", "\\`"),
    ):
        text = text.replace(old, new)
    return text


def render_markdown(stats: list, username: str) -> str:
    """Render the complete README stats block from (language, percentage) tuples for a GitHub user."""
    lines = [
        "## 📊 Technologies across my repositories",
        "",
        "> Auto-generated from public repository language data · "
        "[source](.github/scripts/update_language_stats.py)",
        "",
        "| Language | Percentage | Distribution |",
        "|----------|:----------:|:-------------|",
    ]
    for rank, (lang, pct) in enumerate(stats):
        bar = make_bar(pct)
        badge = make_percentage_badge(pct, rank)
        safe_lang = escape_table_text(lang)
        lines.append(f"| **{safe_lang}** | {badge} | `{bar}` |")

    lines += [
        "",
        "[![Top Languages](https://github-stats-extended.vercel.app/api/top-langs/"
        f"?username={username}&layout=compact&langs_count=10"
        "&theme=material-palenight&hide_border=true&card_width=500)]"
        "(https://github.com/stats-organization/github-stats-extended)",
        "",
        "> *Forks and archived repositories are excluded. "
        "Byte counts reflect the primary language composition "
        "as reported by the GitHub Linguist analyser.*",
    ]
    return "\n".join(lines)


# ── README update ─────────────────────────────────────────────────────────────
def update_readme(new_section: str, readme_path: str) -> None:
    """Replace the README content between the language stats markers with the newly rendered section."""
    with open(readme_path, "r", encoding="utf-8") as fh:
        content = fh.read()

    if MARKER_START not in content or MARKER_END not in content:
        print(
            f"ERROR: markers {MARKER_START!r} / {MARKER_END!r} not found "
            f"in {readme_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    before = content[: content.index(MARKER_START) + len(MARKER_START)]
    after = content[content.index(MARKER_END):]
    updated = f"{before}\n{new_section}\n{after}"

    with open(readme_path, "w", encoding="utf-8") as fh:
        fh.write(updated)
    print(f"README updated: {readme_path}")


# ── Entry point ───────────────────────────────────────────────────────────────
def main() -> None:
    if not GITHUB_TOKEN:
        print("ERROR: GITHUB_TOKEN environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    print(f"Fetching language data for user: {GITHUB_USERNAME}")
    totals = aggregate_languages(GITHUB_USERNAME)

    if not totals:
        print("No language data found. Exiting without modifying README.")
        return

    stats = compute_percentages(totals)
    print("Language percentages:")
    for lang, pct in stats:
        print(f"  {lang}: {pct:.1f}%")

    section = render_markdown(stats, GITHUB_USERNAME)
    update_readme(section, README_PATH)


if __name__ == "__main__":
    main()
