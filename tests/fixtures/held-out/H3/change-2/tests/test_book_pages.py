import unittest

from tests.serving import ServerTestCase


class BookPagesTest(ServerTestCase):
    def test_every_book_carries_its_page_count(self):
        status, payload = self.get("/books")

        self.assertEqual(status, 200)
        for book in payload["books"]:
            self.assertIsInstance(book["pages"], int)


if __name__ == "__main__":
    unittest.main()
