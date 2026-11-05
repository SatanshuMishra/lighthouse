import ast
import os
import unittest

from tests import accept_support as support

CONTRACT_FILES = (
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
PACKAGE = os.path.join(support.ROOT, "lighthouse_tool")
VENDORED = os.path.join(PACKAGE, "contracts")


def python_files():
    return sorted(
        os.path.join(directory, name)
        for directory, _, names in os.walk(PACKAGE)
        if "__pycache__" not in directory.split(os.sep)
        for name in names
        if name.endswith(".py")
    )


def contract_imports(tree):
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names if alias.name == "lighthouse_tool.contract")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level == 0 and module == "lighthouse_tool.contract":
                found.append(module)
            if node.level == 0 and module == "lighthouse_tool":
                found.extend("lighthouse_tool." + alias.name for alias in node.names if alias.name == "contract")
            if node.level == 1 and module == "contract":
                found.append(".contract")
            if node.level == 1 and module == "":
                found.extend("." + alias.name for alias in node.names if alias.name == "contract")
    return found


class Contracts(unittest.TestCase):
    def test_vendored_contracts_equal_the_referee_copies(self):
        for name in CONTRACT_FILES:
            with self.subTest(file=name):
                vendored = os.path.join(VENDORED, name)
                referee = os.path.join(support.REFEREE, name)
                self.assertTrue(os.path.isfile(vendored), "lighthouse_tool/contracts/{} is missing".format(name))
                self.assertTrue(os.path.isfile(referee), "tests/contracts/{} is missing".format(name))
                self.assertEqual(support.read_bytes(vendored), support.read_bytes(referee))

    def test_no_module_keeps_its_own_validator(self):
        self.assertFalse(os.path.exists(os.path.join(PACKAGE, "contract.py")))
        for path in python_files():
            with self.subTest(module=os.path.relpath(path, support.ROOT)):
                with open(path, encoding="utf-8") as handle:
                    tree = ast.parse(handle.read(), filename=path)
                self.assertEqual(contract_imports(tree), [])


if __name__ == "__main__":
    unittest.main()
