import sys
import os
import asyncio
import pytest
from langchain_core.messages import AIMessage, ToolMessage

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from graph.verifier_graph import verifier_supervisor_tools, verifier_researcher_tools

@pytest.mark.asyncio
async def test_verifier_supervisor_tools_handles_all_tool_call_ids():
    ai_msg = AIMessage(
        content="",
        tool_calls=[
            {"name": "think_tool", "args": {"reflection": "thinking..."}, "id": "call_OuKup888RdNyetddwJ4gWvMk"},
            {"name": "ConductResearch", "args": {"company_name": "TCS", "website": "https://tcs.com", "description": "IT services", "research_topic": "verify TCS"}, "id": "call_conduct_1"},
            {"name": "ResearchComplete", "args": {}, "id": "call_complete_1"},
        ]
    )
    
    state = {
        "supervisor_messages": [ai_msg],
        "research_iterations": 0,
        "research_brief": "test brief"
    }
    
    config = {
        "configurable": {
            "max_verifier_iterations": 3,
            "max_concurrent_research_units": 1
        }
    }
    
    cmd = await verifier_supervisor_tools(state, config)
    
    supervisor_msgs = cmd.update.get("supervisor_messages", [])
    returned_ids = {msg.tool_call_id for msg in supervisor_msgs if isinstance(msg, ToolMessage)}
    
    expected_ids = {"call_OuKup888RdNyetddwJ4gWvMk", "call_conduct_1", "call_complete_1"}
    assert returned_ids == expected_ids, f"Expected {expected_ids}, got {returned_ids}"

@pytest.mark.asyncio
async def test_verifier_researcher_tools_handles_all_tool_call_ids():
    ai_msg = AIMessage(
        content="",
        tool_calls=[
            {"name": "think_tool", "args": {"reflection": "evaluating site..."}, "id": "call_think_res_1"},
            {"name": "unknown_tool", "args": {}, "id": "call_unk_res_1"},
        ]
    )
    
    state = {
        "researcher_messages": [ai_msg],
        "tool_call_iterations": 0,
        "research_topic": "test topic",
        "compressed_research": "",
        "raw_notes": []
    }
    
    config = {
        "configurable": {
            "max_react_tool_calls": 5
        }
    }
    
    cmd = await verifier_researcher_tools(state, config)
    
    researcher_msgs = cmd.update.get("researcher_messages", [])
    returned_ids = {msg.tool_call_id for msg in researcher_msgs if isinstance(msg, ToolMessage)}
    
    expected_ids = {"call_think_res_1", "call_unk_res_1"}
    assert returned_ids == expected_ids, f"Expected {expected_ids}, got {returned_ids}"
