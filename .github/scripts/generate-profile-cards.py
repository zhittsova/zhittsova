#!/usr/bin/env python3
"""Render profile cards from public GitHub REST data using only the standard library."""

import json
import os
import textwrap
from collections import Counter
from html import escape
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

USERNAME = "zhittsova"
PINS = ("agri-weather-yield-drivers", "bi-python-uv-project-scaffolder")
COLORS = ("#42c8a5", "#73b7e2", "#ba9ce8", "#e7b26d", "#e88299", "#a9ce79", "#cccbd0", "#88bbb1")


def api(path: str):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "zhittsova-profile-cards"}
    if token := os.environ.get("GH_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    with urlopen(Request(f"https://api.github.com/{path}", headers=headers), timeout=30) as response:
        return json.load(response)


def public_repositories() -> list[dict]:
    repositories = []
    page = 1
    while True:
        batch = api(f"users/{USERNAME}/repos?type=owner&per_page=100&page={page}")
        repositories.extend(repo for repo in batch if not repo["private"] and not repo["fork"])
        if len(batch) < 100:
            return repositories
        page += 1


def search_count(kind: str, query: str) -> int:
    result = api(f"search/{kind}?{urlencode({'q': query, 'per_page': 1})}")
    if result.get("incomplete_results") is not False:
        raise ValueError("GitHub returned incomplete search results")
    count = result.get("total_count")
    if type(count) is not int or count < 0:
        raise ValueError("GitHub returned an invalid search count")
    return count


def label(x: int, y: int, text: str, *, size: int = 16, color: str = "#e8f2ec") -> str:
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}">{escape(text)}</text>'


def card(title: str, height: int, content: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="600" height="{height}" '
        f'viewBox="0 0 600 {height}" role="img" aria-labelledby="title">'
        f'<title id="title">{escape(title)}</title>'
        f'<rect width="600" height="{height}" rx="12" fill="#0f1617"/>'
        '<g font-family="Segoe UI, Ubuntu, Arial, sans-serif">'
        + label(24, 36, title, size=20, color="#42c8a5")
        + content
        + "</g></svg>\n"
    )


def activity_card(repositories: list[dict]) -> str:
    rows = (
        ("Public repositories · excluding forks", len(repositories)),
        ("Commits · public search index", search_count("commits", f"author:{USERNAME} is:public")),
        ("Pull requests opened · public", search_count("issues", f"author:{USERNAME} is:pr is:public")),
        ("Issues opened · public", search_count("issues", f"author:{USERNAME} is:issue is:public")),
        ("Stars earned · owned public repositories", sum(repo["stargazers_count"] for repo in repositories)),
    )
    content = "".join(
        label(24, 78 + i * 34, name) + label(510, 78 + i * 34, f"{value:,}") for i, (name, value) in enumerate(rows)
    )
    return card("Public GitHub activity", 250, content)


def language_card(repositories: list[dict]) -> str:
    languages = Counter()
    for repo in repositories:
        for language, size in api(f"repos/{USERNAME}/{repo['name']}/languages").items():
            if language not in {"HTML", "CSS"}:
                if type(size) is not int or size < 0:
                    raise ValueError("GitHub returned an invalid language size")
                languages[language] += size
    total = sum(languages.values())
    if not total:
        raise ValueError("GitHub returned no language data")
    selected = languages.most_common(7)
    remainder = total - sum(size for _, size in selected)
    if remainder:
        selected.append(("Other", remainder))
    content = label(24, 62, "By code bytes · owned public repositories · excluding HTML/CSS", size=13, color="#a8bcb5")
    x = 24.0
    for i, (language, size) in enumerate(selected):
        width = 552 * size / total
        content += f'<rect x="{x:.3f}" y="80" width="{width:.3f}" height="10" fill="{COLORS[i]}"/>'
        content += label(24, 122 + i * 27, language, color=COLORS[i])
        content += label(510, 122 + i * 27, f"{size / total:.1%}")
        x += width
    return card("Languages in public repositories", 145 + len(selected) * 27, content)


def repository_card(repo: dict) -> str:
    description = textwrap.wrap(repo.get("description") or "", width=65)
    content = "".join(label(24, 74 + i * 24, line, size=15) for i, line in enumerate(description))
    footer_y = 90 + len(description) * 24
    footer = f"{repo.get('language') or 'Repository'} · {repo['stargazers_count']} stars · {repo['forks_count']} forks"
    return card(repo["name"], footer_y + 24, content + label(24, footer_y, footer, size=14, color="#a8bcb5"))


def main() -> None:
    repositories = public_repositories()
    by_name = {repo["name"]: repo for repo in repositories}
    # Finish every API read before replacing any checked-in card.
    cards = {"stats": activity_card(repositories), "top-langs": language_card(repositories)}
    cards.update({f"pin-{name}": repository_card(by_name[name]) for name in PINS})
    destination = Path("profile")
    destination.mkdir(exist_ok=True)
    for name, content in cards.items():
        (destination / f"{name}.svg").write_text(content)
        print(f"Generated {name}.svg")


if __name__ == "__main__":
    main()
