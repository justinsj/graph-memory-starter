"""Against a real server on a real port: an MCP client, the Claude Code hook, and an orchestrator's machines.

- MCP: a client connects over streamable HTTP with a run token and works a task
  through the tools alone: get_brief, graph_context, attach, complete.
- The hook: with KL_API_URL and a key set, the injection comes from the
  service; with the service down, from the graph in-process, as before.
- The reference orchestrator runs a plan on machines it starts (local
  processes). The lease is shorter than a machine takes to start, so only the
  renewals keep the injected token alive. The platform's own credential
  reaches the machine through its environment, and is stored nowhere in the
  knowledge layer.
"""
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kl_support as ks  # noqa: E402
from kl.api import create_app  # noqa: E402
from kl.client import Client  # noqa: E402
from kl.orchestrator import LocalOrchestrator  # noqa: E402

import logging  # noqa: E402
logging.getLogger("mcp").setLevel(logging.CRITICAL)  # a stateless client leaving is logged as a closed stream

ROOT = ks.ROOT
SECRET = "ghp_platform_secret_do_not_store_7731"


class LiveServer(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.svc, cls.boot, cls.admin_p = ks.seeded(cls.tmp, lease_seconds=6)
        cls.url, cls.stop = ks.serve(create_app(cls.svc))
        cls.svc.settings = cls.svc.settings.with_(public_url=cls.url)
        cls.kl = Client(cls.url, cls.boot["key"])
        cls.orch_key = ks.service_account(cls.svc, cls.admin_p)[1]
        cls.orch = Client(cls.url, cls.orch_key)

    @classmethod
    def tearDownClass(cls):
        cls.stop()
        cls.svc.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def plan(self, pid, tasks):
        self.kl.create_project(approve=True, id=pid, title=pid.replace("-", " ").title(), description="For a test.",
                               deliverables=[{"key": "D1", "title": "The thing"}])
        pl = self.kl.propose_plan(pid, "D1", tasks=tasks)
        self.kl.approve(pl["change_request"]["id"])
        return pl["id"]

    # ---- MCP ----------------------------------------------------------------------------------------

    def test_an_mcp_agent_works_a_task_through_the_tools(self):
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
        plan_id = self.plan("mcp-task", [{"key": "t1", "title": "Who approves refunds over £500?",
                                          "checks": [{"id": "done"}]}])
        ex = self.orch.start_execution(plan_id)
        lease = self.orch.lease(ex["id"], "t1", "mcp-agent")

        async def work():
            headers = {"Authorization": f"Bearer {lease['token']}"}
            async with streamablehttp_client(f"{self.url}/mcp", headers=headers) as (read, write, _):
                async with ClientSession(read, write) as s:
                    await s.initialize()
                    tools = sorted(t.name for t in (await s.list_tools()).tools)
                    brief = json.loads((await s.call_tool("get_brief", {})).content[0].text)
                    ctx = json.loads((await s.call_tool("graph_context", {"question": brief["task"]["title"]}))
                                     .content[0].text)
                    await s.call_tool("attach", {"kind": "text", "name": "answer.md", "text": "The Ops Manager."})
                    done = json.loads((await s.call_tool("complete", {"check_results": {"done": True},
                                                                      "outputs": {"answer": "Ops Manager"}}))
                                      .content[0].text)
                    return tools, brief, ctx, done
        tools, brief, ctx, done = asyncio.run(work())
        self.assertTrue({"get_brief", "graph_context", "code_impact", "heartbeat", "attach", "ask_person", "propose",
                         "complete", "fail"} <= set(tools), tools)
        self.assertEqual(brief["task"]["key"], "t1")
        self.assertIn("Ops Manager", ctx["text"])
        self.assertEqual((done["state"], done["task_state"]), ("succeeded", "done"))
        self.assertEqual(self.orch.execution(ex["id"])["state"], "done")

    def test_mcp_with_an_api_key_reads_and_proposes(self):
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        async def work():
            async with streamablehttp_client(f"{self.url}/mcp",
                                             headers={"Authorization": f"Bearer {self.boot['key']}"}) as (r, w, _):
                async with ClientSession(r, w) as s:
                    await s.initialize()
                    found = json.loads((await s.call_tool("graph_search", {"query": "supplier payments"})).content[0].text)
                    bad = json.loads((await s.call_tool("get_brief", {"run_id": "run_nope"})).content[0].text)
                    return found, bad
        found, bad = asyncio.run(work())
        self.assertIn("Supplier payments", [e["name"] for e in found["items"]])
        self.assertEqual(bad["status"], 404)  # problems come back as the tool's answer, not a crash

    # ---- the hook -------------------------------------------------------------------------------------

    def hook(self, env):
        out = subprocess.run([sys.executable, str(ROOT / "src" / "recall_hook.py")], capture_output=True,
                             input=json.dumps({"prompt": "Who approves supplier payments over £2,000?",
                                               "session_id": "hook-test"}).encode(),
                             env={**os.environ, "PYTHONIOENCODING": "utf-8", **env}, timeout=60)
        return json.loads(out.stdout.decode("utf-8"))

    def test_the_hook_asks_the_service_and_falls_back_when_it_is_down(self):
        served = self.hook({"KL_API_URL": self.url, "KL_API_KEY": self.boot["key"],
                            "GRAPH_MEMORY_STATE": str(self.tmp / "state1")})
        self.assertIn("from the knowledge layer", served["systemMessage"])
        want = self.svc.context(self.admin_p, "Who approves supplier payments over £2,000?")["text"]
        self.assertEqual(ks.without_extracted(served["hookSpecificOutput"]["additionalContext"]),
                         ks.without_extracted(want))
        graph = ks.graphs.build(self.tmp / "local")
        down = self.hook({"KL_API_URL": "http://127.0.0.1:9", "KL_API_KEY": "kl_x", "KL_HOOK_TIMEOUT": "1",
                          "GRAPH_MEMORY_DB": str(graph), "GRAPH_MEMORY_STATE": str(self.tmp / "state2")})
        self.assertNotIn("knowledge layer", down["systemMessage"])
        self.assertIn("Founder", down["hookSpecificOutput"]["additionalContext"])

    # ---- the orchestrator -------------------------------------------------------------------------------

    def test_the_orchestrator_runs_a_plan_on_machines_that_start_slower_than_a_lease(self):
        plan_id = self.plan("machines", [
            {"key": "a", "title": "List the refund approval rules", "checks": [{"id": "done"}]},
            {"key": "b", "title": "List the supplier payment rules", "checks": [{"id": "done"}]},
            {"key": "c", "title": "Write the summary", "after": ["a", "b"], "checks": [{"id": "done"}]}])
        orch = LocalOrchestrator(self.orch, offers=["python"], max_machines=2, boot_seconds=9.0,
                                 platform_env={"PLATFORM_REPO_TOKEN": SECRET}, api_url=self.url, log=lambda *a: None)
        out = orch.run_plan(plan_id, timeout=120)
        ex = out["execution"]
        self.assertEqual(ex["state"], "done", json.dumps(out["machine_output"], indent=1))
        self.assertEqual([r["state"] for r in ex["runs"]], ["succeeded"] * 3)  # no lease was lost while booting
        run = self.kl.run(ex["runs"][0]["id"])
        self.assertGreaterEqual(sum(e["type"] == "provisioning" for e in run["events"]), 2)
        art = run["artifacts"][0]
        text = self.kl._req("GET", art["download"], raw=True).text
        self.assertIn("repository credential was available", text)  # the platform's credential reached the machine
        stored = b"".join(p.read_bytes() for p in Path(self.svc.settings.data_dir).rglob("*") if p.is_file())
        self.assertNotIn(SECRET.encode(), stored)  # and the knowledge layer kept none of it


if __name__ == "__main__":
    unittest.main()
