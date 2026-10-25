import re
import unittest
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "cancer_workbench" / "app" / "static"


class ChatLiveRegionTests(unittest.TestCase):
    """The chat thread is rebuilt on every streamed token, so it must not be a live region."""

    @classmethod
    def setUpClass(cls):
        cls.html = (STATIC / "index.html").read_text(encoding="utf-8")
        cls.js = (STATIC / "app.js").read_text(encoding="utf-8")

    def test_thread_is_not_live_and_a_status_region_announces_instead(self):
        thread = re.search(r'<div id="chat-thread"[^>]*>', self.html).group(0)
        self.assertNotIn("aria-live", thread)
        status = re.search(r'<div id="chat-status"[^>]*>', self.html).group(0)
        self.assertIn('role="status"', status)
        self.assertIn('class="sr-only"', status)
        self.assertIn(".sr-only", (STATIC / "style.css").read_text(encoding="utf-8"))

    def test_elapsed_counter_is_hidden_from_screen_readers(self):
        for tag in re.findall(r'<span class="elapsed"[^>]*>', self.js):
            self.assertIn('aria-hidden="true"', tag)

    def test_render_marks_busy_and_restores_focus(self):
        body = self.js[self.js.index("function renderThread("):self.js.index("function renderThreadBody(")]
        self.assertIn('setAttribute("aria-busy"', body)
        self.assertIn("focus({ preventScroll: true })", body)

    def test_delete_buttons_name_their_chat(self):
        self.assertNotIn('aria-label="Delete this chat"', self.js)
        self.assertIn("Delete chat: ${c.title", self.js)


if __name__ == "__main__":
    unittest.main()
