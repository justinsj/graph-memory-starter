"""A reference orchestrator: runs an approved plan's tasks on machines it starts.

It stands in for an execution platform, to show the protocol end to end and to
test it. Here a "machine" is a local process. A real platform starts
containers or VMs, and injects credentials the same way: the run's env
(KL_API_URL, KL_RUN_TOKEN, KL_RUN_ID) beside the platform's own secrets, never
through the knowledge layer.

    orch = LocalOrchestrator(Client(url, service_account_key), offers=["python"])
    orch.run_plan(plan_id)          # start, lease ready tasks, start machines, renew while they boot
"""
import os
import subprocess
import sys
import time
from pathlib import Path

from .client import Client, KLError

ROOT = Path(__file__).resolve().parents[1]


class LocalOrchestrator:
    def __init__(self, client: Client, offers=("python",), max_machines: int = 4, boot_seconds: float = 0.0,
                 platform_env: dict = None, worker: list = None, api_url: str = None, log=print):
        self.kl = client
        self.offers = list(offers)
        self.max_machines = max_machines
        self.boot_seconds = boot_seconds  # how long a machine takes to start; the lease is renewed meanwhile
        self.platform_env = platform_env or {}  # the platform's own credentials, injected beside the run's
        self.worker = worker or [sys.executable, "-m", "kl.worker"]
        self.api_url = api_url  # what machines call (defaults to what the lease says)
        self.log = log
        self.machines = {}  # run id -> (process, started, booted)

    def _spawn(self, lease: dict):
        env = {**os.environ, **self.platform_env, **lease["env"]}
        if self.api_url:
            env["KL_API_URL"] = self.api_url
            env["KL_MCP_URL"] = self.api_url.rstrip("/") + "/mcp"
        env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        proc = subprocess.Popen(self.worker, env=env, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace")
        return proc

    def run_plan(self, plan_id: str, timeout: float = 600, execution_id: str = None) -> dict:
        eid = execution_id or self.kl.start_execution(plan_id)["id"]
        self.log(f"execution {eid} started for plan {plan_id}")
        pending_boot = []  # (lease, boot at)
        end = time.time() + timeout
        outputs = {}
        while time.time() < end:
            ex = self.kl.execution(eid)
            if ex["state"] in ("done", "failed", "cancelled"):
                break
            busy = len(self.machines) + len(pending_boot)
            for task in ex["tasks"]:
                if busy >= self.max_machines:
                    break
                if task["state"] == "ready" and not task["held_by_change_request"]:
                    try:
                        lease = self.kl.lease(eid, task["key"], f"local-{task['key']}", self.offers)
                    except KLError as e:
                        self.log(f"  could not lease {task['key']}: {e}")
                        continue
                    self.kl.run_event(lease["run_id"], "provisioning", "starting a machine")
                    pending_boot.append((lease, time.time() + self.boot_seconds))
                    busy += 1
                    self.log(f"  leased {task['key']} as {lease['run_id']}; machine starting")
            for lease, boot_at in list(pending_boot):
                if time.time() >= boot_at:
                    pending_boot.remove((lease, boot_at))
                    self.machines[lease["run_id"]] = self._spawn(lease)
                    self.log(f"  machine for {lease['run_id']} is up")
                else:  # still booting: keep the lease, and the token, alive
                    self.kl.run_event(lease["run_id"], "provisioning", "still starting")
            for rid, proc in list(self.machines.items()):
                if proc.poll() is not None:
                    out, _ = proc.communicate()
                    outputs[rid] = out
                    del self.machines[rid]
                    self.log(f"  machine for {rid} exited ({proc.returncode})")
            time.sleep(0.2)
        for rid, proc in self.machines.items():
            proc.kill()
            proc.communicate()
        return {"execution": self.kl.execution(eid), "machine_output": outputs}
