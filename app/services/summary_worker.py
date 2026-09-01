"""Backend bridge to the separately deployed AGY summary worker CLI."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from pathlib import Path


class SummaryWorkerError(RuntimeError):
    pass


def _run_worker(report_id: int, force: bool) -> dict:
    root = Path(os.getenv("SUMMARY_WORKER_ROOT", "/home/ubuntu/workspace/external.reports-hub/apps/scrapers/ssh-report-summary-worker"))
    python = os.getenv("SUMMARY_WORKER_PYTHON", "python3")
    command = [python, "-m", "ssh_report_summary_worker.cli", "--report-id", str(report_id), "--write-db"]
    if force:
        command.append("--force")
    env = os.environ.copy()
    paths = [str(root / "src"), "/home/ubuntu/workspace/lib/ssh_library"]
    env["PYTHONPATH"] = os.pathsep.join(paths + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    env.setdefault("SUMMARY_SECRET_FILE", "/home/ubuntu/secrets/workspace/external.reports-hub/apps/scrapers/ssh-report-summary-worker/secrets.json")
    completed = subprocess.run(
        command,
        cwd=root,
        env=env,
        shell=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=int(os.getenv("SUMMARY_WORKER_TIMEOUT_SECONDS", "360")),
        check=False,
    )
    if completed.returncode != 0:
        raise SummaryWorkerError((completed.stderr or completed.stdout or "worker failed")[-2000:])
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise SummaryWorkerError("worker returned invalid JSON") from exc
    if result.get("failed") or not result.get("items"):
        raise SummaryWorkerError(json.dumps(result, ensure_ascii=False))
    item = result["items"][0]
    if item.get("status") not in ("saved", "dry_run"):
        raise SummaryWorkerError(json.dumps(item, ensure_ascii=False))
    return item


async def run_summary_worker(report_id: int, force: bool = False) -> dict:
    return await asyncio.to_thread(_run_worker, report_id, force)
