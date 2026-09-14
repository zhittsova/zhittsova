"""Check the publication boundary for generated profile images."""

import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("cards", Path(__file__).with_name("validate-profile-cards.py"))
cards = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cards)


def svg(content: str) -> bytes:
    return f'<svg xmlns="http://www.w3.org/2000/svg">{content}</svg>'.encode()


class ProfileCardTests(unittest.TestCase):
    def test_accepts_a_rendered_card_with_internal_references(self):
        cards.validate_svg(
            svg(
                '<defs><clipPath id="clip"/></defs><style>rect {clip-path: url("#clip");}</style><text>Commits: 42</text><use href="#clip"/>'
            )
        )

    def test_rejects_existing_placeholder_and_renderer_errors(self):
        for text in cards.ERROR_MESSAGES:
            with self.subTest(text=text), self.assertRaises(ValueError):
                cards.validate_svg(svg(f"<text>{text}</text>"))

    def test_rejects_blank_malformed_and_non_svg_content(self):
        for payload in (svg(""), b"<svg", b"<html>503 Service Unavailable</html>"):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                cards.validate_svg(payload)

    def test_rejects_active_content_and_remote_references(self):
        for content in (
            "<script>alert(1)</script>",
            "<foreignObject/>",
            '<text onload="alert(1)">Stats</text>',
            '<image href="https://example.com/image.svg"/>',
            '<image href="javascript:alert(1)"/>',
            '<style>@import "https://example.com/theme.css";</style>',
        ):
            with self.subTest(content=content), self.assertRaises(ValueError):
                cards.validate_svg(svg(content + "<text>Stats</text>"))

    def test_rejects_entity_declarations(self):
        with self.assertRaises(ValueError):
            cards.validate_svg(b'<!DOCTYPE svg [<!ENTITY text "hidden">]>' + svg("<text>&text;</text>"))


if __name__ == "__main__":
    unittest.main()
