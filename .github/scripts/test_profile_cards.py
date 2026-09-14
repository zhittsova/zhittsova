"""Check the publication boundary for generated profile images."""

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("cards", Path(__file__).with_name("validate-profile-cards.py"))
cards = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cards)

generator_spec = importlib.util.spec_from_file_location(
    "generator", Path(__file__).with_name("generate-profile-cards.py")
)
generator = importlib.util.module_from_spec(generator_spec)
generator_spec.loader.exec_module(generator)


def svg(content: str) -> bytes:
    return f'<svg xmlns="http://www.w3.org/2000/svg">{content}</svg>'.encode()


class ProfileCardTests(unittest.TestCase):
    def test_public_repository_pagination_excludes_private_repositories_and_forks(self):
        repo = {"name": "public", "private": False, "fork": False}
        first_page = [repo] * 98 + [{**repo, "private": True}, {**repo, "fork": True}]
        with patch.object(generator, "api", side_effect=[first_page, [repo]]) as api:
            self.assertEqual(len(generator.public_repositories()), 99)
            self.assertIn("page=2", api.call_args.args[0])

    def test_incomplete_or_invalid_search_counts_fail_generation(self):
        for result in (
            {"incomplete_results": True, "total_count": 12},
            {},
            {"incomplete_results": False, "total_count": -1},
        ):
            with (
                self.subTest(result=result),
                patch.object(generator, "api", return_value=result),
                self.assertRaises(ValueError),
            ):
                generator.search_count("issues", "author:zhittsova is:public")

    def test_repository_metadata_is_escaped_in_svg(self):
        result = generator.repository_card(
            {
                "name": "A & B",
                "description": '<script>alert("x")</script>',
                "language": "Python",
                "stargazers_count": 1,
                "forks_count": 0,
            }
        )
        self.assertIn("&lt;script&gt;", result)
        cards.validate_svg(result.encode())

    def test_languages_exclude_html_and_css_and_retain_small_languages(self):
        data = {f"Language {i}": i + 1 for i in range(9)} | {"HTML": 1000, "CSS": 1000}
        with patch.object(generator, "api", return_value=data):
            result = generator.language_card([{"name": "project"}])
        self.assertIn(">Other</text>", result)
        self.assertIn("20.00%", result)
        cards.validate_svg(result.encode())

    def test_empty_language_data_fails_generation(self):
        with patch.object(generator, "api", return_value={}), self.assertRaises(ValueError):
            generator.language_card([{"name": "project"}])

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
