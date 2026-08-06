import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_company_search_parsing():
    combined_notes = (
        "Company Name: Tata Consultancy Services\n"
        "Official Website: https://www.tcs.com\n"
        "Verified LinkedIn URL: https://www.linkedin.com/company/tata-consultancy-services\n"
        "LinkedIn Confirmed: Yes\n"
    )
    
    urls = re.findall(r'https?://(?:www\.)?linkedin\.com/company/[a-zA-Z0-9\-_%]+', combined_notes, re.IGNORECASE)
    assert len(urls) == 1
    assert urls[0] == "https://www.linkedin.com/company/tata-consultancy-services"

if __name__ == "__main__":
    test_company_search_parsing()
    print("✅ Company search parsing tests passed!")

