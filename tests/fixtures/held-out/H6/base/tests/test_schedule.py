import unittest

from hearthctl.schedule import parse, programme


class ScheduleTest(unittest.TestCase):
    def test_programme_is_in_time_order(self):
        self.assertEqual(programme(["22:00=16", "06:30=20"]), [("06:30", 20.0), ("22:00", 16.0)])

    def test_rejects_a_time_outside_the_day(self):
        with self.assertRaises(ValueError):
            parse("24:10=18")


if __name__ == "__main__":
    unittest.main()
