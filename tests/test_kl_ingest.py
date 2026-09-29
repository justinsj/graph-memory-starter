"""Files in: the six levels of deduplication, extraction checked against the text, and files that disagree.

Each case sends real files from the corpus, or small edits of them, and checks
what the service decided and what the graph now says.
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kl_support as ks  # noqa: E402
from kl import errors  # noqa: E402
from kl.extractors import NoExtractor  # noqa: E402

ROOT = ks.ROOT
POLICY = (ks.CORPUS / "refund-policy.md").read_text(encoding="utf-8")
# A handbook long enough that a forwarded copy is a near copy by any measure: every corpus file, one after another
HANDBOOK = "\n".join(f.read_text(encoding="utf-8") for f in sorted(ks.CORPUS.glob("*.md")))
FORWARDED = "Forwarded from the ops channel by Sam.\n\n" + HANDBOOK  # the same text, with a line on top
EXTRACTION = {json.loads(p.read_text(encoding="utf-8"))["source_doc"]: json.loads(p.read_text(encoding="utf-8"))
              for p in (ROOT / "extraction").glob("*.json")}


class Dedup(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.svc, self.boot, self.p = ks.seeded(self.tmp)  # the corpus, ingested once per process

    def tearDown(self):
        self.svc.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ask(self, q):
        return self.svc.context(self.p, q)["text"]

    def test_the_same_file_twice_is_unchanged(self):
        r = self.svc.ingest(self.p, name="refund-policy.md", data=POLICY.encode())
        self.assertEqual(r["dedup"], "unchanged")
        self.assertEqual(len(self.svc.get_source(self.p, r["document_id"])["versions"]), 1)

    def test_the_same_text_with_other_line_endings_is_the_same_text(self):
        r = self.svc.ingest(self.p, name="refund-policy.md", data=POLICY.replace("\n", "\r\n").encode("utf-8-sig"))
        self.assertEqual(r["dedup"], "unchanged")

    def test_a_renamed_copy_is_another_location_of_the_same_version(self):
        r = self.svc.ingest(self.p, name="copies/refunds-final-v2.md", data=POLICY.encode(), uri="drive://x/2")
        self.assertEqual(r["dedup"], "duplicate")
        src = self.svc.get_source(self.p, r["document_id"])
        self.assertEqual(src["path"], "refund-policy.md")
        self.assertIn({"name": "copies/refunds-final-v2.md", "uri": "drive://x/2", "external_id": None},
                      src["versions"][0]["also_at"])
        self.assertEqual(len(self.svc.list_sources(self.p)["items"]), 9)  # no new document

    def test_a_new_version_replaces_the_old_ones_facts(self):
        text = POLICY.replace("over £500", "over £600").replace("under £500", "under £600")
        x = json.loads(json.dumps(EXTRACTION["refund-policy.md"]).replace("500", "600"))
        r = self.svc.ingest(self.p, name="refund-policy.md", text=text, extraction=x)
        self.assertEqual((r["dedup"], r["status"]), ("new_version", "active"), r)
        versions = self.svc.get_source(self.p, r["document_id"])["versions"]
        self.assertEqual([v["status"] for v in versions], ["superseded", "active"])
        answer = self.ask("Who approves a £550 refund in October 2026?")
        self.assertIn("600", answer)
        self.assertNotIn("Refunds over £500 need Ops Manager approval", answer)

    def handbook(self):
        return self.svc.ingest(self.p, name="handbook.md", text=HANDBOOK, extraction={"nodes": [], "edges": []})

    def test_a_near_copy_is_linked_and_left_out(self):
        self.assertEqual(self.handbook()["status"], "active")
        r = self.svc.ingest(self.p, name="fwd-handbook.md", text=FORWARDED)
        self.assertEqual((r["dedup"], r["status"]), ("near_duplicate", "duplicate"), r)
        self.assertGreaterEqual(r["duplicate_of"]["similarity"], 0.9)
        self.assertIn("fwd-handbook.md", [d["path"] for d in self.svc.list_sources(self.p)["items"]])
        self.assertEqual(self.svc.get_source(self.p, r["document_id"])["versions"][0]["status"], "duplicate")

    def test_a_short_file_with_a_word_changed_is_not_a_near_copy(self):
        near = POLICY.replace("Ops Manager", "Operations Manager", 1)  # 66 words: Jaccard 0.86, under 0.9
        r = self.svc.ingest(self.p, name="refund-policy-copy.md", text=near)
        self.assertEqual(r["dedup"], "new")

    def test_a_near_copy_can_be_sent_to_a_person(self):
        self.handbook()
        r = self.svc.ingest(self.p, name="fwd-handbook.md", text=FORWARDED, near_duplicates="review")
        self.assertEqual(r["status"], "held")
        cr = self.svc.list_change_requests(self.p, state="open")["items"][0]
        self.assertEqual(cr["ops"], [{"op": "activate_version", "version": r["version_id"]}])
        self.svc.reject_change_request(self.p, cr["id"], "it is the same policy")
        self.assertEqual(self.svc.get_source(self.p, r["document_id"])["versions"][0]["status"], "rejected")

    def test_the_same_fact_from_two_files_is_one_claim_with_two_sources(self):
        quote = "Refunds over £500 require approval by the Ops Manager before payment is released."
        node = next(n for n in EXTRACTION["refund-policy.md"]["nodes"] if n["name"] == "Refund approvals")
        claim = next(c for c in node["claims"] if c["quote"] == quote)
        faq = f"# Refunds FAQ\n\nWho approves big refunds? {quote}\n"
        r = self.svc.ingest(self.p, name="refunds-faq.md", text=faq,
                            extraction={"nodes": [{"name": "Refund approvals", "type": "POLICY", "claims": [claim]}],
                                        "edges": [], "aliases": []})
        self.assertEqual(r["status"], "active", r)
        ent = self.svc.search(self.p, "refund approvals")["items"][0]
        claims = self.svc.get_entity(self.p, ent["id"])["claims"]
        same = [c for c in claims if c["text"] == claim["text"]]
        self.assertEqual(len(same), 1)
        self.assertEqual(sorted(s["doc"] for s in same[0]["sources"]), ["refund-policy.md", "refunds-faq.md"])
        self.assertEqual(self.svc.get_claim(self.p, same[0]["id"])["id"], same[0]["id"])

    def test_two_files_that_disagree_go_to_a_person(self):
        draft = "# Refund policy draft\n\nRefunds over £1,000 need Ops Manager approval.\n"
        x = {"nodes": [{"name": "Refund approvals", "type": "POLICY", "claims": [
            {"kind": "threshold", "text": "Refunds over £1,000 need Ops Manager approval", "amount": 1000,
             "unit": "GBP", "quote": "Refunds over £1,000 need Ops Manager approval."}]}], "edges": [], "aliases": []}
        r = self.svc.ingest(self.p, name="refund-policy-draft.md", text=draft, extraction=x)
        self.assertEqual(r["status"], "held", r)
        cr = self.svc.list_change_requests(self.p, state="open")["items"][0]
        self.assertIn("two threshold claims hold at once", cr["reason"])
        kinds = [o["op"] for o in cr["ops"]]
        self.assertEqual(kinds[0], "activate_version")
        self.assertIn("retract_source", kinds)
        with self.assertRaises(errors.Invalid):  # activating alone would not build
            self.svc.approve_change_request(self.p, cr["id"], ops=[1])
        self.svc.approve_change_request(self.p, cr["id"])
        ent = next(e for e in self.svc.search(self.p, "refund approvals")["items"] if e["name"] == "Refund approvals")
        texts = [c["text"] for c in self.svc.get_entity(self.p, ent["id"])["claims"]]
        self.assertIn("Refunds over £1,000 need Ops Manager approval", texts)
        self.assertNotIn("Refunds over £500 require approval by the Ops Manager before payment is released", texts)
        retracted = [d for d in self.svc.list_sources(self.p, include_deleted=True)["items"] if d["deleted_at"]]
        self.assertIn("refund-policy.md", [d["path"] for d in retracted])

    def test_an_extraction_that_misquotes_is_refused(self):
        x = {"nodes": [{"name": "Refund approvals", "type": "POLICY", "claims": [
            {"kind": "rule", "text": "Refunds are free", "quote": "Every refund is free of charge."}]}]}
        r = self.svc.ingest(self.p, name="notes.md", text="Refunds are handled by the team.\n", extraction=x)
        self.assertEqual(r["status"], "failed")
        self.assertTrue(any("does not contain the quote" in p for p in r["problems"]), r["problems"])

    def test_without_an_extractor_a_document_waits_for_its_extraction(self):
        tmp = Path(tempfile.mkdtemp())
        svc = ks.make_service(tmp, extractor=NoExtractor())
        try:
            _, p = ks.workspace(svc)
            r = svc.ingest(p, name="org-chart.md", data=(ks.CORPUS / "org-chart.md").read_bytes())
            self.assertEqual(r["status"], "awaiting_extraction")
            self.assertEqual(r["job"]["status"], "waiting")
            done = svc.submit_extraction(p, r["document_id"], EXTRACTION["org-chart.md"])
            self.assertEqual(done["status"], "active", done)
            self.assertIn("Priya Patel", svc.context(p, "Who is the Support Lead?")["text"])
        finally:
            svc.close()
            shutil.rmtree(tmp, ignore_errors=True)

    def test_a_manifest_says_what_to_upload_and_what_to_retract(self):
        for name in ("a.md", "b.md"):
            self.svc.ingest(self.p, name=name, collection="drive", text=f"# {name}\n\nNothing yet.\n",
                            extraction={"nodes": [], "edges": []})
        import hashlib
        same = hashlib.sha256(b"# a.md\n\nNothing yet.\n").hexdigest()
        out = self.svc.manifest(self.p, "drive", [{"name": "a.md", "sha256": same},
                                                   {"name": "c.md", "sha256": "0" * 64}], retract_missing=True)
        self.assertEqual([u["item"] for u in out["upload"]], ["c.md"])
        self.assertEqual([u["item"] for u in out["unchanged"]], ["a.md"])
        self.assertEqual([r["path"] for r in out["retracted"]], ["drive/b.md"])

    def test_retracting_a_source_takes_its_facts_out_and_restoring_brings_them_back(self):
        doc = next(d for d in self.svc.list_sources(self.p)["items"] if d["path"] == "supplier-payments.md")
        q = "Who approves supplier payments over £2,000?"
        self.assertIn("[supplier-payments.md]", self.ask(q))
        self.svc.retract_source(self.p, doc["id"])
        self.assertNotIn("[supplier-payments.md]", self.ask(q))
        self.svc.restore_source(self.p, doc["id"])
        self.assertIn("[supplier-payments.md]", self.ask(q))

    def test_a_pdf_needs_its_text(self):
        with self.assertRaises(errors.Invalid):
            self.svc.ingest(self.p, name="scan.pdf", data=b"%PDF-1.4 ...")

    def test_the_storage_limit_holds(self):
        self.svc.update_settings(self.p, {"max_storage_bytes": 10})
        with self.assertRaises(errors.TooMany):
            self.svc.ingest(self.p, name="more.md", text="x" * 100)

    def test_a_transcript_becomes_a_change_request_quoting_it(self):
        import cases
        case = cases.load(ROOT / "projects" / "cases" / "01-new-project")
        r = self.svc.ingest(self.p, name=Path(case["input"]).name, kind="transcript", text=case["text"],
                            changes=case["diff"]["changes"], on=case["diff"]["on"])
        self.assertEqual(r["status"], "active")
        cr_id = r["job"]["result"]["change_request"]
        cr = self.svc.get_change_request(self.p, cr_id)
        self.assertEqual(cr["problems"], [], cr)
        self.assertEqual(self.svc.list_projects(self.p)["items"], [])  # nothing until a person approves
        self.svc.approve_change_request(self.p, cr_id)
        records = self.svc._records(self.p.workspace_id)
        self.assertEqual(cases.check(case["expect"], {}, case["diff"], records), [])
        rec = records["helpdesk-migration"]
        self.assertEqual(rec["description"]["source"], f"inputs/{Path(case['input']).name}")


if __name__ == "__main__":
    unittest.main()
