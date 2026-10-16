import unittest

from tests.serving import TOKEN, ServerTestCase


class WithdrawTest(ServerTestCase):
    def test_withdraws_a_piece_from_the_queue(self):
        status, payload = self.request("DELETE", "/pieces/2", token=TOKEN)
        self.assertEqual(status, 200)
        self.assertEqual(payload["withdrawn"]["title"], "Lidded jar")
        _, listing = self.request("GET", "/pieces")
        self.assertEqual([piece["id"] for piece in listing["pieces"]], [1, 3])
        self.assertEqual(self.request("GET", "/pieces/2")[0], 404)

    def test_a_piece_not_in_the_queue_is_not_found(self):
        status, _ = self.request("DELETE", "/pieces/42", token=TOKEN)
        self.assertEqual(status, 404)
        _, listing = self.request("GET", "/pieces")
        self.assertEqual(len(listing["pieces"]), 3)

    def test_the_queue_itself_cannot_be_deleted(self):
        status, _ = self.request("DELETE", "/pieces", token=TOKEN)
        self.assertEqual(status, 404)

    def test_withdrawing_without_the_studio_token_is_refused(self):
        status, _ = self.request("DELETE", "/pieces/2")
        self.assertEqual(status, 401)
        self.assertEqual(self.request("GET", "/pieces/2")[0], 200)


if __name__ == "__main__":
    unittest.main()
