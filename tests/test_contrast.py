import json
import subprocess
import sys
import unittest

from tests import scratch

COMMAND_TIMEOUT_SECONDS = 60


def linear_channel(value):
    fraction = value / 255
    if fraction <= 0.04045:
        return fraction / 12.92
    return ((fraction + 0.055) / 1.055) ** 2.4


def relative_luminance(red, green, blue):
    return 0.2126 * linear_channel(red) + 0.7152 * linear_channel(green) + 0.0722 * linear_channel(blue)


def wcag_ratio(foreground, background):
    first = relative_luminance(*foreground)
    second = relative_luminance(*background)
    lighter = max(first, second)
    darker = min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def channels(hex_digits):
    return tuple(int(hex_digits[index:index + 2], 16) for index in (0, 2, 4))


def lighthouse_contrast(test, *arguments):
    completed = subprocess.run(
        [sys.executable, scratch.LIGHTHOUSE, "contrast", *arguments],
        env=scratch.environment(scratch.make_home(test)),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_SECONDS,
    )
    return completed.returncode, completed.stdout, completed.stderr


def measurement(test, *arguments):
    code, stdout, stderr = lighthouse_contrast(test, *arguments)
    test.assertEqual(code, 0, stdout + stderr)
    return json.loads(stdout)


class ContrastTest(unittest.TestCase):
    def test_declared_colours_give_the_wcag_ratio(self):
        expected = wcag_ratio(channels("903B4C"), channels("F0DCD2"))
        self.assertEqual(round(expected, 2), 5.44)

        measured = measurement(self, "--foreground", "#903B4C", "--background", "#F0DCD2", "--source", "declared")

        self.assertEqual(measured, {"ratio": 5.44, "threshold": 4.5, "status": "pass", "source": "declared"})

    def test_flutter_colour_is_read(self):
        expected = wcag_ratio(channels("903B4C"), channels("F0DCD2"))
        self.assertEqual(round(expected, 2), 5.44)

        measured = measurement(self, "--foreground", "0xFF903B4C", "--background", "0xFFF0DCD2", "--source", "declared")

        self.assertEqual(measured["ratio"], 5.44)
        self.assertEqual(measured["status"], "pass")

    def test_tree_colours_below_the_threshold_fail(self):
        expected = wcag_ratio(channels("777777"), channels("FFFFFF"))
        self.assertEqual(round(expected, 2), 4.48)
        self.assertLess(expected, 4.5)

        measured = measurement(self, "--foreground", "#777777", "--background", "#FFFFFF", "--source", "tree")

        self.assertEqual(measured["ratio"], 4.48)
        self.assertEqual(measured["threshold"], 4.5)
        self.assertEqual(measured["status"], "fail")
        self.assertEqual(measured["source"], "tree")

    def test_pixel_sample_near_the_threshold_could_not_run(self):
        expected = wcag_ratio((155, 77, 91), (240, 220, 210))
        self.assertEqual(round(expected, 2), 4.40)
        self.assertLessEqual(abs(expected - 4.5), 0.3)

        measured = measurement(
            self, "--foreground", "rgb(155, 77, 91)", "--background", "rgb(240, 220, 210)", "--source", "pixels"
        )

        self.assertEqual(measured["ratio"], 4.4)
        self.assertEqual(measured["status"], "could-not-run")
        self.assertEqual(measured["source"], "pixels")
        self.assertIsInstance(measured.get("reason"), str)
        self.assertTrue(measured["reason"])

    def test_pixel_sample_far_below_fails(self):
        expected = wcag_ratio(channels("AAAAAA"), channels("FFFFFF"))
        self.assertEqual(round(expected, 2), 2.32)
        self.assertGreater(abs(expected - 4.5), 0.3)

        measured = measurement(self, "--foreground", "#AAAAAA", "--background", "#FFFFFF", "--source", "pixels")

        self.assertEqual(measured["ratio"], 2.32)
        self.assertEqual(measured["status"], "fail")
        self.assertEqual(measured["source"], "pixels")

    def test_pixel_sample_far_above_passes(self):
        expected = wcag_ratio(channels("000000"), channels("FFFFFF"))
        self.assertEqual(round(expected, 2), 21.0)

        measured = measurement(self, "--foreground", "#000000", "--background", "#FFFFFF", "--source", "pixels")

        self.assertEqual(measured["ratio"], 21.0)
        self.assertEqual(measured["status"], "pass")
        self.assertEqual(measured["source"], "pixels")

    def test_large_text_uses_three(self):
        expected = wcag_ratio(channels("949494"), channels("FFFFFF"))
        self.assertEqual(round(expected, 2), 3.03)
        self.assertLess(expected, 4.5)

        measured = measurement(
            self, "--foreground", "#949494", "--background", "#FFFFFF", "--source", "declared", "--large"
        )

        self.assertEqual(measured["ratio"], 3.03)
        self.assertEqual(measured["threshold"], 3.0)
        self.assertEqual(measured["status"], "pass")

    def test_translucent_colour_could_not_run(self):
        measured = measurement(self, "--foreground", "#903B4C80", "--background", "#F0DCD2", "--source", "declared")

        self.assertEqual(measured["status"], "could-not-run")
        self.assertIsInstance(measured.get("reason"), str)
        self.assertTrue(measured["reason"])

    def test_unreadable_colour_is_refused(self):
        code, stdout, stderr = lighthouse_contrast(
            self, "--foreground", "red", "--background", "#FFFFFF", "--source", "declared"
        )

        self.assertEqual(code, 2, stdout + stderr)
        refusal = json.loads(stdout)
        self.assertIsInstance(refusal.get("error"), str)
        self.assertIn("red", refusal["error"])


if __name__ == "__main__":
    unittest.main()
