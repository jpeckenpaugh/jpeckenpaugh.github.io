import unittest

from app.ui.text import format_text


class TestTextFormatting(unittest.TestCase):
    def test_format_text_success(self) -> None:
        self.assertEqual(
            format_text("Hello {name}.", name="Kara"),
            "Hello Kara.",
        )

    def test_format_text_missing_key(self) -> None:
        self.assertEqual(
            format_text("Hello {name}."),
            "Hello {name}.",
        )

    def test_format_text_invalid_braces(self) -> None:
        self.assertEqual(
            format_text("Hello {name"),
            "Hello {name",
        )


if __name__ == "__main__":
    unittest.main()
