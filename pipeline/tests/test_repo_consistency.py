"""Repo-wide guards (idea from travienphi tests/test_repo_consistency.py).

These tests read files only; they never call the network. They enforce PLAN Công đoạn 1:
no secret in the repo or in CI logs, and AGENTS.md §4–5 (minimal workflow permissions,
actions pinned by commit SHA).
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
ALLOWED_SECRETS = {"CLOUDFLARE_API_TOKEN", "REVIEW_PASSWORD", "PURGE_TOKEN", "GOOGLE_API_KEY"}
# Secret nào chỉ được nằm trong env của bước chạy lệnh nào (D-019).
SECRET_STEP_COMMAND = {
    "CLOUDFLARE_API_TOKEN": ("wrangler",),
    "REVIEW_PASSWORD": ("wrangler secret put REVIEW_PASSWORD",),
    "PURGE_TOKEN": ("wrangler secret put PURGE_TOKEN",),
    "GOOGLE_API_KEY": (
        "pay-pipeline pdf-gather",
        "pay-pipeline extra-pay-crawl",
    ),  # Drive API, chỉ đọc file công khai (D-059)
}
# Job duy nhất được ghi repo: tạo Release chứa tệp nguồn (D-014). Không ra Internet, không secret.
WRITE_JOBS = {
    ("fetch-sources.yml", "archive"): {"contents": "write"},
    ("import-districts.yml", "publish-report"): {"contents": "write"},
    ("import-schedules.yml", "publish-report"): {"contents": "write"},
    ("import-federal.yml", "publish-report"): {"contents": "write"},
    ("pdf-pipeline.yml", "archive"): {"contents": "write"},
    ("pdf-pipeline-resume.yml", "archive"): {"contents": "write", "actions": "read"},
    ("pdf-eval.yml", "publish-report"): {"contents": "write"},
    ("extra-pay-crawl.yml", "archive"): {"contents": "write"},
}
SECRET_REF = re.compile(r"secrets\.([A-Za-z0-9_]+)")
PINNED = re.compile(r"^[\w.-]+/[\w.-]+(/[\w./-]+)?@[0-9a-f]{40}$")


def load(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def steps(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for job in workflow.get("jobs", {}).values():
        out.extend(job.get("steps", []))
    return out


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [ROOT / line for line in result.stdout.splitlines() if line]


def test_workflows_exist() -> None:
    names = {p.name for p in WORKFLOWS}
    assert {"ci.yml", "deploy.yml", "bootstrap-cloudflare.yml", "fetch-sources.yml"} <= names


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
class TestWorkflow:
    def test_top_level_permissions_read_only(self, path: Path) -> None:
        wf = load(path)
        assert wf.get("permissions") == {"contents": "read"}
        for name, job in wf["jobs"].items():
            perms = job.get("permissions", {})
            allowed = WRITE_JOBS.get((path.name, name))
            if allowed is not None:
                assert perms == allowed, f"{name}: quyền khác danh sách cho phép"
            else:
                assert "write" not in json.dumps(perms), f"{name} xin quyền ghi"

    def test_actions_pinned_by_sha(self, path: Path) -> None:
        for step in steps(load(path)):
            if "uses" in step:
                assert PINNED.match(step["uses"]), step["uses"]

    def test_only_allowed_secrets(self, path: Path) -> None:
        names = set(SECRET_REF.findall(path.read_text(encoding="utf-8")))
        assert names <= ALLOWED_SECRETS, names

    def test_secrets_only_in_step_env_of_wrangler_steps(self, path: Path) -> None:
        wf = load(path)
        assert "secrets." not in json.dumps(wf.get("env", {})), "secret ở env cấp workflow"
        for job in wf["jobs"].values():
            assert "secrets." not in json.dumps(job.get("env", {})), "secret ở env cấp job"
        for step in steps(wf):
            env = json.dumps(step.get("env", {}))
            run = step.get("run", "")
            assert "secrets." not in run, "secret dùng thẳng trong lệnh"
            assert "secrets." not in json.dumps(step.get("with", {})), "secret trong with:"
            for name in set(SECRET_REF.findall(env)):
                commands = SECRET_STEP_COMMAND[name]
                assert any(c in run for c in commands), f"{name} ở bước không chạy {commands}"

    def test_no_shell_tracing(self, path: Path) -> None:
        # `set -x` in lại lệnh kèm biến môi trường đã mở rộng.
        for step in steps(load(path)):
            assert not re.search(r"set\s+-[a-z]*x", step.get("run", "")), step.get("name")


def test_write_jobs_do_not_fetch_or_use_secrets() -> None:
    for (file_name, job_name), _ in WRITE_JOBS.items():
        job = load(ROOT / ".github" / "workflows" / file_name)["jobs"][job_name]
        text = json.dumps(job)
        assert "secrets." not in text
        for tool in ("pay-pipeline", "curl", "wget", "uv run", "pip install", "npm"):
            assert tool not in text, f"{job_name} không được chạy {tool}"


def test_no_secret_values_in_repo() -> None:
    patterns = [
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        re.compile(r"CLOUDFLARE_API_TOKEN\s*[=:]\s*['\"]?[A-Za-z0-9_-]{20,}"),
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    ]
    for path in tracked_files():
        if not path.is_file() or path.suffix in {".png", ".ico", ".pdf"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in patterns:
            assert not pattern.search(text), f"{path.relative_to(ROOT)} có giá trị giống bí mật"


def test_wrangler_config_has_no_secrets() -> None:
    text = (ROOT / "apps" / "web" / "wrangler.jsonc").read_text(encoding="utf-8")
    # Biến môi trường thường nằm trong "vars"; bí mật phải đặt bằng `wrangler secret put`.
    assert not re.search(r'"[A-Z_]*(TOKEN|SECRET|PASSWORD|API_KEY)[A-Z_]*"\s*:', text)


def test_preview_and_production_use_different_databases() -> None:
    text = (ROOT / "apps" / "web" / "wrangler.jsonc").read_text(encoding="utf-8")
    names = re.findall(r'"database_name":\s*"([^"]+)"', text)
    assert names == ["pay-schedules", "pay-schedules-preview"]


# Một tài liệu chỉ là bảng lương của một học khu (D-066). Ngoại lệ: học khu tiểu học và trung học
# dùng chung một bảng (Montana), đã kiểm tay.
SHARED_SEED_URLS = {
    "https://resources.finalsite.net/images/v1784925041/billingsschoolsorg/izpgx2muwqwlieraxaui/2026-27BEASalaryMatrix-WithMastersandPHDStipendAdded.pdf",
    "https://frazer.k12.mt.us/files/page/1865/Pay_Scales_2025.pdf",
    "https://www.blueponyk12.com/employment/certified-salary-schedule",
}


def test_seed_urls_belong_to_one_district() -> None:
    import csv

    owners: dict[str, set[str]] = {}
    with (ROOT / "pipeline" / "sources" / "schedule-urls.csv").open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            owners.setdefault(row["url"], set()).add(row["nces_id"])
    shared = {u: len(n) for u, n in owners.items() if len(n) > 1 and u not in SHARED_SEED_URLS}
    assert not shared, shared
