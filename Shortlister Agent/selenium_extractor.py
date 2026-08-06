import os
import re
import urllib.parse
from typing import Optional
import httpx

LINKEDIN_COMPANY_REGEX = re.compile(
    r'https?://(?:[a-zA-Z0-9-]+\.)*linkedin\.com/(?:company|school)/[a-zA-Z0-9\-_%]+',
    re.IGNORECASE
)

def _normalize_website_url(url: str) -> str:
    if not url or str(url).strip().lower() in ("not found", "none", "nan", ""):
        return ""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url

def _clean_linkedin_url(url: str) -> str:
    """Clean and normalize extracted LinkedIn URL."""
    if not url:
        return ""
    url = url.rstrip("./,;\"'")
    parsed = urllib.parse.urlparse(url)
    cleaned = f"https://www.linkedin.com{parsed.path}"
    cleaned = cleaned.rstrip("/")
    return cleaned

def extract_linkedin_from_website_selenium(website_url: str, company_name: str = "", timeout: int = 12) -> Optional[str]:
    """
    Deterministic extraction of company LinkedIn URL from the website's homepage.
    1. Uses headless Selenium Chrome browser (rendering client-side JS).
    2. Searches all <a> tags and page source for linkedin.com/company/ or linkedin.com/school/ links.
    3. Falls back to httpx fast HTML scan if Selenium fails or driver is unavailable.
    Returns the cleaned LinkedIn URL if found, else None.
    """
    target_url = _normalize_website_url(website_url)
    if not target_url:
        return None

    tag = f"[Company: {company_name}]" if company_name else f"[Website: {target_url}]"
    print(f"   {tag} 🔎 [Selenium Extractor]: Checking homepage '{target_url}' for LinkedIn links...")

    # Attempt 1: Selenium Headless Browser
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By

        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-extensions")
        options.add_argument("--blink-settings=imagesEnabled=false")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        service = None
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            service = Service(ChromeDriverManager().install())
        except Exception:
            service = Service()

        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(timeout)
        driver.set_script_timeout(timeout)

        try:
            driver.get(target_url)
            
            # Check <a> tags href attributes
            anchors = driver.find_elements(By.TAG_NAME, "a")
            for anchor in anchors:
                try:
                    href = anchor.get_attribute("href") or ""
                    if "linkedin.com/company/" in href.lower() or "linkedin.com/school/" in href.lower():
                        match = LINKEDIN_COMPANY_REGEX.search(href)
                        if match:
                            found = _clean_linkedin_url(match.group(0))
                            print(f"   {tag} 🎯 [Selenium Found]: Matched LinkedIn URL on homepage: {found}")
                            return found
                except Exception:
                    continue

            # Check full rendered page_source if anchors didn't match
            page_src = driver.page_source or ""
            matches = LINKEDIN_COMPANY_REGEX.findall(page_src)
            if matches:
                found = _clean_linkedin_url(matches[0])
                print(f"   {tag} 🎯 [Selenium Found (Source)]: Matched LinkedIn URL on homepage: {found}")
                return found

        finally:
            try:
                driver.quit()
            except Exception:
                pass

    except Exception as exc:
        print(f"   {tag} ⚠️ [Selenium Warning]: Selenium fetch failed ({exc}). Trying fast HTTP fallback...")

    # Attempt 2: Fast HTTP/HTML Fallback Scan (httpx)
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        with httpx.Client(timeout=8.0, follow_redirects=True, headers=headers) as client:
            resp = client.get(target_url)
            if resp.status_code == 200:
                matches = LINKEDIN_COMPANY_REGEX.findall(resp.text)
                if matches:
                    found = _clean_linkedin_url(matches[0])
                    print(f"   {tag} 🎯 [HTTP Fallback Found]: Matched LinkedIn URL on homepage: {found}")
                    return found
    except Exception as exc:
        print(f"   {tag} ⚠️ [HTTP Fallback Warning]: Could not fetch {target_url}: {exc}")

    print(f"   {tag} ℹ️  [Selenium Extractor]: No LinkedIn URL found on homepage for '{target_url}'.")
    return None
