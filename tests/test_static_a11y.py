import unittest
from html.parser import HTMLParser
from pathlib import Path

INDEX = Path(__file__).resolve().parents[1] / "cancer_workbench" / "app" / "static" / "index.html"


class _Ids(HTMLParser):
    def __init__(self):
        super().__init__()
        self.by_id, self.textareas = {}, []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("id"):
            self.by_id[a["id"]] = (tag, a)
        if tag == "textarea":
            self.textareas.append(a)


class AssistantMarkupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = _Ids()
        cls.page.feed(INDEX.read_text(encoding="utf-8"))

    def test_composer_describes_its_keyboard_shortcuts(self):
        message = next(a for a in self.page.textareas if a.get("aria-label") == "Message")
        self.assertEqual(message.get("aria-describedby"), "ask-keys")
        self.assertIn("ask-keys", self.page.by_id)

    def test_labelled_containers_have_a_role_that_takes_a_name(self):
        self.assertEqual(self.page.by_id["model-pickers"][1].get("role"), "group")
        self.assertTrue(self.page.by_id["ask-form"][1].get("aria-label"))

    def test_every_aria_reference_points_at_an_element(self):
        for tag, attrs in self.page.by_id.values():
            for key in ("aria-describedby", "aria-labelledby", "aria-controls"):
                for ref in (attrs.get(key) or "").split():
                    self.assertIn(ref, self.page.by_id, f"{key}={ref} on <{tag}>")


if __name__ == "__main__":
    unittest.main()
