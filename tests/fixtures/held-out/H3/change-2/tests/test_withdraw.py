import unittest

from tests.serving import ServerTestCase


class WithdrawTest(ServerTestCase):
    def test_withdraws_a_piece_from_the_queue(self):
        status, payload = self.request("DELETE", "/pieces/2")
        self.assertEqual(status, 200)
        self.assertEqual(payload["withdrawn"]["title"], "Lidded jar")
        _, listing = self.request("GET", "/pieces")
        self.assertEqual([piece["id"] for piece in listing["pieces"]], [1, 3])
        self.assertEqual(self.request("GET", "/pieces/2")[0], 404)

    def test_a_piece_not_in_the_queue_is_not_found(self):
        status, _ = self.request("DELETE", "/pieces/42")
        self.assertEqual(status, 404)
        _, listing = self.request("GET", "/pieces")
        self.assertEqual(len(listing["pieces"]), 3)

    def test_the_queue_itself_cannot_be_deleted(self):
        status, _ = self.request("DELETE", "/pieces")
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
