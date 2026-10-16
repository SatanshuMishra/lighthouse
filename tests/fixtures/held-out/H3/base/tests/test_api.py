import unittest

from tests.serving import ServerTestCase


class ApiTest(ServerTestCase):
    def test_books(self):
        status, payload = self.get("/books")

        self.assertEqual(status, 200)
        self.assertTrue(payload["books"])
        for book in payload["books"]:
            self.assertLessEqual({"id", "title", "author", "added"}, set(book))

    def test_loans(self):
        status, payload = self.get("/loans")

        self.assertEqual(status, 200)
        self.assertTrue(payload["loans"])
        for loan in payload["loans"]:
            self.assertLessEqual({"id", "book", "member", "due"}, set(loan))

    def test_unknown_path(self):
        status, payload = self.get("/nowhere")

        self.assertEqual(status, 404)
        self.assertEqual(payload, {"error": "not found"})


if __name__ == "__main__":
    unittest.main()
