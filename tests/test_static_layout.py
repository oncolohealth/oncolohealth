"""Phone-width layout guards for the static stylesheet."""
import re
import unittest
from pathlib import Path

STYLE = (Path(__file__).resolve().parents[1] / "cancer_workbench" / "app" / "static" / "style.css").read_text(encoding="utf-8")


def phone_block() -> str:
    start = STYLE.index("@media (max-width: 960px) {")
    return STYLE[start:STYLE.index("\n}\n", start)]


class PhoneLayoutTests(unittest.TestCase):
    def test_progress_items_wrap_long_words(self):
        # PROGRESS.md lines can hold long paths or run-together words; they widened the page to 641px at 375px.
        self.assertRegex(STYLE, r"\.items li \{[^}]*grid-template-columns: 22px minmax\(0, 1fr\)")
        self.assertRegex(STYLE, r"\.items li \.txt \{[^}]*overflow-wrap: anywhere")

    def test_phone_lets_download_pills_wrap_and_tightens_tables(self):
        block = phone_block()
        self.assertIn(".tier-rows .pill { white-space: normal; }", block)
        self.assertTrue(re.search(r"\.records th, \.records td \{ padding-left: 8px; padding-right: 8px; \}", block))


if __name__ == "__main__":
    unittest.main()
