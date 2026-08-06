import sys
import os
import asyncio
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from graph.shortlister import cleaner

@pytest.mark.asyncio
async def test_cleaner_removes_not_found_and_sorts():
    sample_enriched = [
        {"name": "Comp A", "revenue_ttm": 100, "website": "https://compa.com"},
        {"name": "Comp B", "revenue_ttm": 500, "website": "NOT FOUND"},
        {"name": "Comp C", "revenue_ttm": 300, "website": "https://compc.com"},
        {"name": "Comp D", "revenue_ttm": 400, "website": "https://compd.com"},
    ]
    state = {"enriched_companies": sample_enriched}
    config = {"configurable": {"top_n_companies": 2}}
    
    cmd = await cleaner(state, config)
    cleaned = cmd.update.get("cleaned_companies", [])
    
    assert len(cleaned) == 2
    assert cleaned[0]["name"] == "Comp D"  # 400 revenue
    assert cleaned[1]["name"] == "Comp C"  # 300 revenue

if __name__ == "__main__":
    asyncio.run(test_cleaner_removes_not_found_and_sorts())
    print("✅ All cleaner tests passed!")
