#!/usr/bin/env python3
"""Reject missing, unsafe, blank or error SVGs before publishing profile cards."""

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ERROR_MESSAGES = (
    "card unavailable",
    "source service temporarily unavailable",
    "something went wrong",
    "could not fetch",
    "rate limit exceeded",
    "please deploy your own instance",
)


def validate_svg(payload: bytes) -> None:
    if len(payload) > 1_000_000:
        raise ValueError("card exceeds 1 MB")
    if b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
        raise ValueError("XML declarations are not allowed")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise ValueError("invalid XML") from exc
    if root.tag != "{http://www.w3.org/2000/svg}svg":
        raise ValueError("expected an SVG document")
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1].lower()
        if tag in {"script", "foreignobject"}:
            raise ValueError("active SVG content is not allowed")
        for key, value in element.attrib.items():
            attribute = key.rsplit("}", 1)[-1].lower()
            if attribute.startswith("on"):
                raise ValueError("event handlers are not allowed")
            if attribute in {"href", "src"} and not value.startswith("#"):
                raise ValueError("external references are not allowed")
        if tag == "style":
            css = element.text or ""
            urls = re.findall(r"url\(\s*([^)]*)\)", css, re.I)
            if re.search(r"@import", css, re.I) or any(not url.strip(" \t\r\n\"'").startswith("#") for url in urls):
                raise ValueError("external CSS references are not allowed")
    labels = " ".join("".join(el.itertext()) for el in root.iter() if el.tag.endswith("}text"))
    labels = " ".join(labels.split())
    if not labels:
        raise ValueError("card has no visible text")
    if any(message in labels.lower() for message in ERROR_MESSAGES):
        raise ValueError(f"renderer returned an error or placeholder card: {labels[:600]}")


def main(paths: list[str]) -> int:
    if not paths:
        print("Pass at least one SVG path", file=sys.stderr)
        return 1
    for filename in paths:
        try:
            validate_svg(Path(filename).read_bytes())
        except (OSError, ValueError) as exc:
            print(f"ERROR: {filename}: {exc}", file=sys.stderr)
            return 1
        print(f"Validated {filename}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
