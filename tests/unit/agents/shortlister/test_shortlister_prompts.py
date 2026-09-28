"""Hermetic unit tests for the Shortlister prompt constants."""

from leadgen.agents.shortlister import prompts

# ── query formulator prompt ───────────────────────────────────────────────────


def test_company_search_prompt_format():
    company_name = "TATA ELXSI"
    website = "https://www.tataelxsi.com"

    query = f'"{company_name}" "{website}" site:linkedin.com/company'
    assert company_name in query
    assert website in query
    assert "site:linkedin.com/company" in query


def test_query_formulator_instructions_format():
    rendered = prompts.query_formulator_instructions.format(user_input="Tech companies in India")

    assert "Tech companies in India" in rendered
    assert "ScreenerQuery" in rendered
    assert "sector" in rendered
    assert "TradingView" in rendered


# ── supervisor prompt ─────────────────────────────────────────────────────────


def test_lead_verifier_supervisor_prompt_format():
    rendered = prompts.lead_verifier_supervisor_prompt.format(
        date="2024-01-02",
        max_concurrent_research_units=5,
        max_researcher_iterations=9,
    )

    assert "2024-01-02" in rendered
    assert "Maximum 5 parallel sub-agents per round." in rendered
    assert "Maximum 9 iterations." in rendered
    assert "site:linkedin.com/company" in rendered
    assert "ConductResearch" in rendered
    assert "ResearchComplete" in rendered


# ── researcher prompt ─────────────────────────────────────────────────────────


def test_verifier_researcher_prompt_format_and_guidance():
    rendered = prompts.verifier_researcher_prompt.format(mcp_prompt="MCP-TOOLS-PLACEHOLDER")

    assert "MCP-TOOLS-PLACEHOLDER" in rendered
    assert "site:linkedin.com/company" in rendered
    assert "{company_name}" in rendered
    assert "{website}" in rendered
    assert "{description}" in rendered
    assert "Verified LinkedIn URL:" in rendered
    assert "LinkedIn Confirmed: Yes / No" in rendered


# ── compression prompts ───────────────────────────────────────────────────────


def test_compress_verifier_human_message_has_structured_output_block():
    message = prompts.compress_verifier_human_message

    assert message.format() == message
    assert "Company Name:" in message
    assert "Official Website:" in message
    assert "Verified LinkedIn URL:" in message
    assert "LinkedIn Confirmed: Yes / No" in message


def test_compress_verifier_system_prompt_has_no_placeholders():
    system_prompt = prompts.compress_verifier_system_prompt

    assert system_prompt.format() == system_prompt
    assert "synthesis agent" in system_prompt


# ── final report prompt ───────────────────────────────────────────────────────


def test_final_verification_report_prompt_format():
    rendered = prompts.final_verification_report_prompt.format(
        candidate_companies="CANDIDATE-BLOCK",
        findings="FINDINGS-BLOCK",
    )

    assert "CANDIDATE-BLOCK" in rendered
    assert "FINDINGS-BLOCK" in rendered
    assert '"companies"' in rendered
    assert '"linkedin_confirmed"' in rendered


# ── every documented prompt constant exists ───────────────────────────────────


def test_all_prompt_constants_exist():
    for name in (
        "query_formulator_instructions",
        "lead_verifier_supervisor_prompt",
        "verifier_researcher_prompt",
        "compress_verifier_human_message",
        "compress_verifier_system_prompt",
        "final_verification_report_prompt",
    ):
        value = getattr(prompts, name)
        assert isinstance(value, str)
        assert value.strip()
