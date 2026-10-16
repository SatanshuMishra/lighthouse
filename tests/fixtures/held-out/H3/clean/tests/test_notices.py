import unittest

from tests.serving import ServerTestCase


class NoticesTest(ServerTestCase):
    def test_one_notice_per_loan(self):
        status, payload = self.get("/loan-notices")

        self.assertEqual(status, 200)
        self.assertEqual([notice["loan"] for notice in payload["notices"]], [1, 2])

    def test_notice_names_the_book_and_a_readable_day(self):
        _, payload = self.get("/loan-notices")

        self.assertEqual(payload["notices"][0]["message"], "Please return Dune by Tue 05 Mar 2024.")


if __name__ == "__main__":
    unittest.main()
