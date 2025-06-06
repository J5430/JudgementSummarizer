import streamlit as st
import requests
from bs4 import BeautifulSoup
import json
import os

SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")  # Set this in your environment or Streamlit secrets

def search_serpapi(query):
    params = {
        "engine": "google",
        "q": f"site:indiankanoon.org {query}",
        "api_key": SERPAPI_API_KEY,
    }
    response = requests.get("https://serpapi.com/search", params=params)
    response.raise_for_status()
    return response.json()

def fetch_case_html(url):
    headers = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/114.0.0.0 Safari/537.36")
    }
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    return resp.text

def parse_structured_data(html):
    # Example: search for a script tag containing JSON structured data
    soup = BeautifulSoup(html, "html.parser")
    scripts = soup.find_all("script", type="application/ld+json")
    for script in scripts:
        try:
            data = json.loads(script.string)
            if isinstance(data, dict) and "court" in data:
                return data
        except Exception:
            continue
    # fallback: return None if no structured data found
    return None

def main():
    st.title("⚖️ Judgment Summarizer")

    case_input = st.text_input("Enter a case (Syntax: X vs Y 2007)")
    if not case_input:
        st.info("Please enter a case name to search.")
        return

    with st.spinner("Searching IndiaKanoon via SerpAPI..."):
        try:
            serp_results = search_serpapi(case_input)
        except Exception as e:
            st.error(f"SerpAPI search failed: {e}")
            return

    organic = serp_results.get("organic_results", [])
    if not organic:
        st.warning("No results found from SerpAPI.")
        return

    # Use the first result link from indiankanoon.org
    case_url = None
    for result in organic:
        link = result.get("link")
        if link and "indiankanoon.org" in link:
            case_url = link
            break

    if not case_url:
        st.warning("No valid IndiaKanoon case URL found in search results.")
        return

    st.markdown(f"**Found case URL:** [Link]({case_url})")

    with st.spinner("Fetching case page..."):
        try:
            html = fetch_case_html(case_url)
        except requests.HTTPError as e:
            st.error(f"Failed to fetch case page: {e}")
            return

    structured_data = parse_structured_data(html)
    if structured_data:
        st.subheader("Structured Case Data")
        st.json(structured_data)
    else:
        st.warning("No structured data found on the case page.")
        # Optional: Show raw HTML snippet preview
        st.text_area("Raw HTML snippet", html[:2000])

if __name__ == "__main__":
    main()
