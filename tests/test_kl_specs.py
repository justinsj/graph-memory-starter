"""The service's own OpenSpec (openspec/specs/): in the format, and every scenario verified by its test.

A scenario is verified by the test named after it, by the same rule the service
uses to link a customer's tests to their specs (kl.openspec.link_tests).
"""
import ast
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kl_support as ks  # noqa: E402
from kl import openspec  # noqa: E402

ROOT = ks.ROOT


def spec_files() -> dict:
    return {p.relative_to(ROOT).as_posix(): p.read_text(encoding="utf-8")
            for p in (ROOT / "openspec" / "specs").glob("*/spec.md")}


def test_names() -> list:
    names = []
    for f in sorted((ROOT / "tests").glob("test_kl_*.py")):
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                names.append(f"{f.stem}.{node.name}")
    return names


class ServiceSpecs(unittest.TestCase):

    def test_the_specs_are_in_the_format(self):
        docs, problems = openspec.specs_to_extraction(spec_files())
        self.assertEqual(problems, [])
        self.assertEqual({d["source_doc"].split("/")[2] for d in docs},
                         {"sources", "review", "plans", "runs", "context", "openspec", "workspaces", "events",
                          "impact"})

    def test_every_scenario_is_verified_by_its_test(self):
        scenarios = openspec.scenarios(spec_files())
        linked = {e["target"] for e in openspec.link_tests(test_names(), scenarios)}
        self.assertEqual(sorted(set(scenarios) - linked), [])
        self.assertGreaterEqual(len(scenarios), 70)


if __name__ == "__main__":
    unittest.main()
