import os
import unittest

from tests import contract_check, scratch

PRODUCT_CONTRACTS = os.path.join(scratch.ROOT, "lighthouse_tool", "contracts")
PRODUCT_FILES = (
    "validator.py",
    "h11-interphase-record.schema.json",
    "h13-lighthouse-verdict-line.schema.json",
    "h14-lighthouse-findings.schema.json",
    "h15-pr-fields.schema.json",
    "h16-pr-render.schema.json",
    "k1-acceptance.schema.json",
    "k2-locked.schema.json",
    "k3-check-result.schema.json",
)


def read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


class ContractCopiesTest(unittest.TestCase):
    def test_product_contracts_match_the_referee_copies(self):
        for name in PRODUCT_FILES:
            referee = os.path.join(contract_check.CONTRACTS, name)
            product = os.path.join(PRODUCT_CONTRACTS, name)
            self.assertTrue(os.path.isfile(referee), referee)
            self.assertTrue(os.path.isfile(product), "{} is missing".format(product))
            self.assertEqual(read_bytes(referee), read_bytes(product), "{} differs from {}".format(product, referee))


if __name__ == "__main__":
    unittest.main()
