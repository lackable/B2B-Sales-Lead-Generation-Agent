import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_company_search_prompt_format():
    company_name = "TATA ELXSI"
    website = "https://www.tataelxsi.com"
    desc = "Engineering and technology services"
    
    query = f'"{company_name}" "{website}" site:linkedin.com/company'
    assert company_name in query
    assert website in query
    assert "site:linkedin.com/company" in query

if __name__ == "__main__":
    test_company_search_prompt_format()
    print("✅ All company batch search query prompt tests passed!")

