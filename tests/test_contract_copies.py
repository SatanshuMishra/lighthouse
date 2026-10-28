import os
import unittest

from tests import contract_check, scratch

PRODUCT_CONTRACTS = os.path.join(scratch.ROOT, "lighthouse_tool", "contracts")
SCHEMA_NAMES = ("k1-acceptance.schema.json", "k3-check-result.schema.json")


def read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


class ContractCopiesTest(unittest.TestCase):
    def test_product_schemas_match_the_referee_copies(self):
        for name in SCHEMA_NAMES:
            referee = os.path.join(contract_check.CONTRACTS, name)
            product = os.path.join(PRODUCT_CONTRACTS, name)
            self.assertTrue(os.path.isfile(referee), referee)
            self.assertTrue(os.path.isfile(product), "{} is missing".format(product))
            self.assertEqual(read_bytes(referee), read_bytes(product), "{} differs from {}".format(product, referee))


if __name__ == "__main__":
    unittest.main()
