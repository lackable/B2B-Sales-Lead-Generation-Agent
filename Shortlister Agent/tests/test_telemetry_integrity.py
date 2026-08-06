import asyncio
import json
import logging
import sys
import tempfile
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from logging_utils.config import StructuredLoggerAdapter
from logging_utils.handlers import StructuredFileHandler
from logging_utils.lifecycle import subagent_lifecycle
from logging_utils.registry import emit_event, get_logger, register_logger
from logging_utils.snapshots import sanitize_decision_makers


class CapturingLogger:
    def __init__(self):
        self.events = []

    def event(self, event_type, data, **kwargs):
        self.events.append({"event_type": event_type, "data": dict(data), **kwargs})


def test_registry_logging_survives_logging_package_swap(tmp_path):
    previous_logger = get_logger()
    previous_logging_package = sys.modules.get("logging_")
    log_path = tmp_path / "shortlister.jsonl"
    logger = logging.getLogger("test.shortlister.registry")
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.INFO)
    handler = StructuredFileHandler(str(log_path))
    logger.addHandler(handler)
    register_logger(StructuredLoggerAdapter(logger, agent="shortlister", run_id="test-run"))
    sys.modules["logging_"] = ModuleType("logging_")

    try:
        assert emit_event(
            "company_contacts_snapshot",
            {"company": "Acme", "contact_count": 1},
            component="test.registry",
        )
        handler.flush()
    finally:
        handler.close()
        logger.handlers.clear()
        register_logger(previous_logger)
        if previous_logging_package is None:
            sys.modules.pop("logging_", None)
        else:
            sys.modules["logging_"] = previous_logging_package

    event = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert event["event_type"] == "company_contacts_snapshot"
    assert event["agent"] == "shortlister"
    assert event["data"]["company"] == "Acme"


def test_concurrent_company_and_branch_lifecycles_are_balanced():
    previous_logger = get_logger()
    capture = CapturingLogger()
    register_logger(capture)

    async def run_branch(company, root_id, branch):
        execution_id = f"{root_id}:{branch}"
        with subagent_lifecycle(
            company=company,
            execution_id=execution_id,
            parent_execution_id=root_id,
            branch=branch,
            component="test.lifecycle",
        ):
            await asyncio.sleep(0)

    async def run_company(index):
        company = f"Company {index}"
        root_id = f"run-{index}"
        with subagent_lifecycle(
            company=company,
            execution_id=root_id,
            parent_execution_id="pipeline",
            branch="company_research",
            component="test.lifecycle",
        ) as terminal_data:
            await asyncio.gather(
                run_branch(company, root_id, "company_linkedin_verifier"),
                run_branch(company, root_id, "linkedin_contact_finder"),
            )
            terminal_data["contact_count"] = index

    async def run_all_companies():
        await asyncio.gather(*[run_company(index) for index in range(10)])

    try:
        asyncio.run(run_all_companies())
    finally:
        register_logger(previous_logger)

    starts = [event for event in capture.events if event["event_type"] == "subagent_start"]
    terminals = [event for event in capture.events if event["event_type"] == "subagent_end"]
    company_starts = [event for event in starts if event["data"]["branch"] == "company_research"]
    company_terminals = [event for event in terminals if event["data"]["branch"] == "company_research"]
    branch_starts = [event for event in starts if event["data"]["branch"] != "company_research"]
    branch_terminals = [event for event in terminals if event["data"]["branch"] != "company_research"]

    assert len(company_starts) == 10
    assert len(company_terminals) == 10
    assert len(branch_starts) == 20
    assert len(branch_terminals) == 20
    assert {event["data"]["execution_id"] for event in starts} == {
        event["data"]["execution_id"] for event in terminals
    }


def test_lifecycle_emits_error_before_terminal():
    previous_logger = get_logger()
    capture = CapturingLogger()
    register_logger(capture)

    try:
        try:
            with subagent_lifecycle(
                company="Acme",
                execution_id="root",
                parent_execution_id="pipeline",
                branch="company_research",
                component="test.lifecycle",
            ):
                raise RuntimeError("boom")
        except RuntimeError:
            pass
    finally:
        register_logger(previous_logger)

    assert [event["event_type"] for event in capture.events] == [
        "subagent_start",
        "subagent_error",
        "subagent_end",
    ]
    assert capture.events[-1]["data"]["status"] == "error"


def test_snapshot_sanitizer_excludes_urls_and_preserves_roles():
    contacts = sanitize_decision_makers([
        {"name": "Ada Lovelace", "position": "CTO", "linkedin_url": "https://example.test/ada"},
        {"name": "Grace Hopper", "role": "VP Engineering", "email": "grace@example.test"},
    ])

    assert contacts == [
        {"name": "Ada Lovelace", "role": "CTO"},
        {"name": "Grace Hopper", "role": "VP Engineering"},
    ]
    assert all("linkedin_url" not in contact and "email" not in contact for contact in contacts)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as temp_dir:
        test_registry_logging_survives_logging_package_swap(Path(temp_dir))
    test_concurrent_company_and_branch_lifecycles_are_balanced()
    test_lifecycle_emits_error_before_terminal()
    test_snapshot_sanitizer_excludes_urls_and_preserves_roles()
    print("telemetry integrity tests passed")
