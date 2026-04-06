#!/usr/bin/env python3
"""Generate profile card SVGs with validation and resilient fallback behavior."""

import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Final

SVG_START_RE: Final[re.Pattern[str]] = re.compile(
    r"^[\s]*(<\?xml\s+[^>]*\?>\s*)?<svg([\s>])",
    re.IGNORECASE,
)
DISALLOWED_SVG_RE: Final[re.Pattern[str]] = re.compile(
    r"<\s*/?\s*(script|foreignObject)([\s>])",
    re.IGNORECASE,
)
DISALLOWED_EVENT_HANDLER_RE: Final[re.Pattern[str]] = re.compile(
    r"\son[a-z][\w:-]*\s*=",
    re.IGNORECASE,
)
DISALLOWED_JS_URL_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:href|xlink:href|src)\s*=\s*['\"]\s*javascript:",
    re.IGNORECASE,
)
DISALLOWED_EXTERNAL_REF_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:href|xlink:href|src)\s*=\s*['\"]\s*(?:https?:)?//",
    re.IGNORECASE,
)
PROFILE_DIR: Final[Path] = Path("profile")
SCRIPT_DIR: Final[Path] = Path(__file__).resolve().parent
PLACEHOLDER_TEMPLATE_PATH: Final[Path] = SCRIPT_DIR / "card-unavailable-template.svg"
BASE_GRS_URL: Final[str] = "https://github-readme-stats.vercel.app"


@dataclass(frozen=True, slots=True)
class CardSpec:
    url: str
    output: Path
    placeholder_title: str


def as_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc
    if value < 1:
        raise ValueError(f"{name} must be >= 1, got {value}")
    return value


def as_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def write_placeholder_svg(output: Path, title: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    template = PLACEHOLDER_TEMPLATE_PATH.read_text(encoding="utf-8")
    svg = template.replace("{{TITLE}}", escape(title))
    output.write_text(svg, encoding="utf-8")


def build_grs_url(path: str, params: dict[str, str]) -> str:
    query = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    return f"{BASE_GRS_URL}{path}?{query}"


def validate_svg(payload: bytes, content_type: str) -> str | None:
    normalized_ct = content_type.split(";", 1)[0].strip().lower()
    if normalized_ct != "image/svg+xml":
        return f"unexpected Content-Type: {normalized_ct or '<missing>'}"

    text = payload.decode("utf-8", errors="replace")
    prefix = text[:512].replace("\r", "")
    if SVG_START_RE.match(prefix) is None:
        return "invalid SVG document start"

    if DISALLOWED_SVG_RE.search(text):
        return "disallowed SVG content (script/foreignObject)"

    if DISALLOWED_EVENT_HANDLER_RE.search(text):
        return "disallowed SVG event-handler attribute"

    if DISALLOWED_JS_URL_RE.search(text):
        return "disallowed javascript URL in SVG"

    if DISALLOWED_EXTERNAL_REF_RE.search(text):
        return "disallowed external reference in SVG"

    return None


def save_svg(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(delete=False, dir=path.parent) as tmp:
        tmp.write(payload)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def fetch_svg(
    *,
    url: str,
    output: Path,
    placeholder_title: str,
    retry_count: int,
    retry_delay_seconds: int,
    allow_placeholder_fallback: bool,
    fail_on_generator_errors: bool,
) -> bool:
    last_error = "unknown error"
    had_generator_like_failure = False

    # Retry if upstream is down (like now with http code 503)
    for attempt in range(1, retry_count + 1):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "Accept": "image/svg+xml,*/*;q=0.8",
                },
            )
            with urllib.request.urlopen(req, timeout=45) as response:
                content_type = response.headers.get("Content-Type", "")
                payload = response.read()

            validation_error = validate_svg(payload, content_type)
            if validation_error is None:
                save_svg(output, payload)
                return True

            last_error = validation_error
            had_generator_like_failure = True
        except urllib.error.HTTPError as exc:
            last_error = f"HTTP {exc.code}: {exc.reason}"
            if 400 <= exc.code < 500:
                had_generator_like_failure = True
        except urllib.error.URLError as exc:
            last_error = f"URL error: {exc.reason}"
        except TimeoutError:
            last_error = "request timed out"
        except Exception as exc:  # noqa: BLE001
            last_error = f"unexpected error: {exc}"
            had_generator_like_failure = True

        if attempt < retry_count:
            print(
                f"WARN: attempt {attempt}/{retry_count} failed for {output}: {last_error}",
                flush=True,
            )
            time.sleep(retry_delay_seconds)

    print(
        f"WARN: all {retry_count} attempt(s) failed for {output}: {last_error}",
        flush=True,
    )

    if fail_on_generator_errors and had_generator_like_failure:
        print(
            f"ERROR: fail-on-generator-errors enabled; refusing fallback for {output} after: {last_error}",
            file=sys.stderr,
            flush=True,
        )
        return False

    if output.exists():
        print(f"WARN: keeping existing file {output}", flush=True)
        return True

    if allow_placeholder_fallback:
        print(
            f"WARN: no existing file for {output}; writing placeholder card", flush=True
        )
        try:
            write_placeholder_svg(output, placeholder_title)
            return True
        except (OSError, ValueError) as exc:
            print(f"WARN: failed to write placeholder for {output}: {exc}", flush=True)
            return False

    return False


def build_cards(owner: str) -> tuple[CardSpec, ...]:
    return (
        CardSpec(
            url=build_grs_url(
                "/api",
                {
                    "username": owner,
                    "show_icons": "true",
                    "include_all_commits": "true",
                    "rank_icon": "percentile",
                    "hide_border": "true",
                    "theme": "transparent",
                    "custom_title": "GitHub Activity",
                    "cache_seconds": "86400",
                },
            ),
            output=PROFILE_DIR / "stats.svg",
            placeholder_title="GitHub Activity Card Unavailable",
        ),
        CardSpec(
            url=build_grs_url(
                "/api/top-langs/",
                {
                    "username": owner,
                    "layout": "compact",
                    "langs_count": "8",
                    "hide": "html,css",
                    "hide_border": "true",
                    "theme": "transparent",
                    "custom_title": "Core Languages",
                    "cache_seconds": "86400",
                },
            ),
            output=PROFILE_DIR / "top-langs.svg",
            placeholder_title="Top Languages Card Unavailable",
        ),
        CardSpec(
            url=build_grs_url(
                "/api/pin/",
                {
                    "username": "zhittsova",
                    "repo": "agri-weather-yield-drivers",
                    "show_owner": "false",
                    "hide_border": "true",
                    "theme": "transparent",
                    "cache_seconds": "86400",
                },
            ),
            output=PROFILE_DIR / "pin-agri-weather-yield-drivers.svg",
            placeholder_title="agri-weather-yield-drivers Card Unavailable",
        ),
        CardSpec(
            url=build_grs_url(
                "/api/pin/",
                {
                    "username": "zhittsova",
                    "repo": "bi-python-uv-project-scaffolder",
                    "show_owner": "false",
                    "hide_border": "true",
                    "theme": "transparent",
                    "cache_seconds": "86400",
                },
            ),
            output=PROFILE_DIR / "pin-bi-python-uv-project-scaffolder.svg",
            placeholder_title="bi-python-uv-project-scaffolder Card Unavailable",
        ),
    )


def main() -> int:
    owner = os.getenv("OWNER") or os.getenv("GITHUB_REPOSITORY_OWNER")
    if not owner:
        print("OWNER (or GITHUB_REPOSITORY_OWNER) must be set", file=sys.stderr)
        return 1

    try:
        retry_count = as_int("RETRY_COUNT", 2)
        retry_delay_seconds = as_int("RETRY_DELAY_SECONDS", 2)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    allow_placeholder_fallback = as_bool("ALLOW_PLACEHOLDER_FALLBACK", False)
    fail_on_generator_errors = as_bool(
        "FAIL_ON_GENERATOR_ERRORS",
        as_bool("STRICT_REUSE_ON_GENERATOR_ERRORS", False),
    )

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    cards = build_cards(owner)

    failures = 0
    for card in cards:
        ok = fetch_svg(
            url=card.url,
            output=card.output,
            placeholder_title=card.placeholder_title,
            retry_count=retry_count,
            retry_delay_seconds=retry_delay_seconds,
            allow_placeholder_fallback=allow_placeholder_fallback,
            fail_on_generator_errors=fail_on_generator_errors,
        )
        if not ok:
            failures += 1

    if failures:
        print(
            f"Failed to generate {failures} card(s) and no fallback file was available",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
