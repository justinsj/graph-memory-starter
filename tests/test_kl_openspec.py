"""OpenSpec as a source: requirements dated by their archived changes, and tests linked to the scenarios they name.

The repository is the sample shop with an openspec/ folder: a requirement added
on 1 August (refunds over £250 need approval), raised to £500 on 20 September,
and a refund window removed that day. One change is still open, and it is not a
fact until it is archived.
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kl_support as ks  # noqa: E402
from kl import openspec  # noqa: E402

ROOT = ks.ROOT
SHOP = ROOT / "codegraph" / "cases" / "shop"
FIXTURE = ROOT / "tests" / "fixtures" / "openspec-shop"
REQ = "refunds: Approval threshold"
SMALL = "refunds: Approval threshold: Small refund needs no approval"


class OpenSpecInTheGraph(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        repo = cls.tmp / "repo"
        shutil.copytree(SHOP, repo)
        shutil.copytree(FIXTURE / "openspec", repo / "openspec")
        cls.svc = ks.make_service(cls.tmp)
        _, cls.p = ks.workspace(cls.svc)
        cls.r = cls.svc.ingest(cls.p, name="shop", kind="code", data=ks.zip_dir(repo))

    @classmethod
    def tearDownClass(cls):
        cls.svc.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def entity(self, name):
        hit = next(e for e in self.svc.search(self.p, name, limit=50)["items"] if e["name"] == name)
        return self.svc.get_entity(self.p, hit["id"])

    def test_the_code_zip_is_indexed_and_its_specs_read(self):
        self.assertEqual(self.r["status"], "active", self.r)
        types = {e["type"] for e in self.svc.search(self.p, "approval threshold refund", limit=100)["items"]}
        self.assertTrue({"REQUIREMENT", "SCENARIO", "FUNCTION"} <= types, types)

    def test_a_modified_requirement_ends_the_old_claim_the_day_its_change_was_archived(self):
        claims = {c["text"]: (c["valid_from"], c["valid_to"]) for c in self.entity(REQ)["claims"]}
        self.assertEqual(claims["Refunds over £250 SHALL need approval before payment."], ("2026-08-01", "2026-09-20"))
        self.assertEqual(claims["Refunds over £500 SHALL need approval before payment."], ("2026-09-20", None))

    def test_a_removed_requirement_ends_that_day(self):
        claims = self.entity("refunds: Refund window")["claims"]
        self.assertEqual([(c["valid_from"], c["valid_to"]) for c in claims], [("2026-08-01", "2026-09-20")])

    def test_context_answers_as_of_a_date(self):
        august = self.svc.context(self.p, REQ, as_of="2026-08-15")["text"]
        october = self.svc.context(self.p, REQ, as_of="2026-10-01")["text"]
        self.assertIn("£250", august)
        self.assertNotIn("£500 SHALL", august)
        self.assertIn("£500", october)
        self.assertNotIn("£250 SHALL", october)

    def test_an_open_change_is_not_a_fact(self):
        names = [e["name"] for e in self.svc.search(self.p, "currency", limit=50)["items"]]
        self.assertNotIn("refunds: Currency", names)

    def test_a_test_that_names_a_scenario_verifies_it(self):
        scen = self.entity(SMALL)
        self.assertEqual([t["name"].rsplit(".", 1)[-1] for t in scen["verified_by"]],
                         ["test_small_refund_needs_no_approval"])
        self.assertIn("needs_approval", [c["name"].rsplit(".", 1)[-1] for c in scen["implemented_by"]])
        req = self.entity(REQ)
        self.assertEqual(len(req["verified_by"]), 2)

    def test_a_code_change_says_which_requirements_are_at_stake(self):
        impact = self.svc.code_impact(self.p, "needs_approval")
        stake = {s["scenario"] for sym in impact["symbols"] for s in sym["requirements_at_stake"]}
        self.assertEqual(stake, {SMALL, "refunds: Approval threshold: Large refund needs approval"})
        self.assertIn("is called by", impact["text"])

    def test_the_parser_checks_the_format(self):
        _, problems = openspec.specs_to_extraction({"openspec/specs/x/spec.md": (
            "## Purpose\nX.\n\n## Requirements\n### Requirement: Loose\nIt might do things.\n")})
        self.assertIn("openspec/specs/x/spec.md: Loose: a requirement says SHALL or MUST", problems)
        self.assertIn("openspec/specs/x/spec.md: Loose: a requirement has at least one #### Scenario:", problems)


if __name__ == "__main__":
    unittest.main()
