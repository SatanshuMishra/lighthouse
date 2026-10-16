import unittest

from tests.serving import TOKEN, ServerTestCase


class StudioTokenTest(ServerTestCase):
    def queue_length(self):
        _, payload = self.request("GET", "/pieces")
        return len(payload["pieces"])

    def test_reading_the_queue_needs_no_token(self):
        self.assertEqual(self.request("GET", "/pieces")[0], 200)
        self.assertEqual(self.request("GET", "/pieces/1")[0], 200)

    def test_queueing_without_a_token_is_refused(self):
        status, payload = self.request("POST", "/pieces", {"maker": "Ada", "title": "Mug"})
        self.assertEqual(status, 401)
        self.assertIn("token", payload["error"])
        self.assertEqual(self.queue_length(), 3)

    def test_queueing_with_another_token_is_refused(self):
        status, _ = self.request("POST", "/pieces", {"maker": "Ada", "title": "Mug"}, "guess")
        self.assertEqual(status, 401)
        self.assertEqual(self.queue_length(), 3)

    def test_queueing_with_the_studio_token_is_accepted(self):
        status, _ = self.request("POST", "/pieces", {"maker": "Ada", "title": "Mug"}, TOKEN)
        self.assertEqual(status, 201)
        self.assertEqual(self.queue_length(), 4)


if __name__ == "__main__":
    unittest.main()
