import unittest

from tests.serving import ServerTestCase


class QueueApiTest(ServerTestCase):
    def test_lists_the_sample_queue_in_order(self):
        status, payload = self.request("GET", "/pieces")
        self.assertEqual(status, 200)
        self.assertEqual([piece["id"] for piece in payload["pieces"]], [1, 2, 3])
        self.assertEqual(set(payload["pieces"][0]), {"id", "maker", "title", "glaze"})

    def test_shows_one_piece(self):
        status, payload = self.request("GET", "/pieces/2")
        self.assertEqual((status, payload["title"]), (200, "Lidded jar"))

    def test_a_missing_piece_is_not_found(self):
        status, _ = self.request("GET", "/pieces/42")
        self.assertEqual(status, 404)

    def test_queues_a_new_piece(self):
        status, piece = self.request("POST", "/pieces", {"maker": "Ada", "title": "Mug"})
        self.assertEqual(status, 201)
        self.assertEqual((piece["id"], piece["glaze"]), (4, "none"))
        _, payload = self.request("GET", "/pieces")
        self.assertEqual(payload["pieces"][-1], piece)

    def test_refuses_a_piece_without_a_title(self):
        status, _ = self.request("POST", "/pieces", {"maker": "Ada"})
        self.assertEqual(status, 400)
        _, payload = self.request("GET", "/pieces")
        self.assertEqual(len(payload["pieces"]), 3)

    def test_unknown_paths_are_not_found(self):
        status, payload = self.request("GET", "/kilns")
        self.assertEqual((status, payload), (404, {"error": "not found"}))


if __name__ == "__main__":
    unittest.main()
