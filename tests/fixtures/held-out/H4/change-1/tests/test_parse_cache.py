import unittest

from quillmark.parser import parse


class ParseCacheTest(unittest.TestCase):
    def test_a_template_is_parsed_once(self):
        template = "Reminder: {event} starts at {time}."
        hits = parse.cache_info().hits

        first = parse(template)
        second = parse(template)

        self.assertIs(first, second)
        self.assertEqual(parse.cache_info().hits, hits + 1)

    def test_cached_segments_match_a_fresh_parse(self):
        template = "Invoice {number} is due on {due}."

        self.assertEqual(parse(template), parse.__wrapped__(template))


if __name__ == "__main__":
    unittest.main()
