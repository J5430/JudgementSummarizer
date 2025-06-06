import streamlit as st
import requests
from bs4 import BeautifulSoup
import subprocess
import json
import os
from urllib.parse import urlparse

# === Config ===
SERPAPI_API_KEY = st.secrets.get("SERPAPI_API_KEY") or os.getenv("SERPAPI_API_KEY")
MODEL_NAME = "gemma3:4b"  # or your local model name

# Cache folder for Streamlit Cloud
CACHE_DIR = os.path.join(os.getcwd(), ".cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# === Helper functions ===

@st.cache_data(show_spinner=False)
def serpapi_search(query: str):
    params = {
        "engine": "google",
        "q": f"site:indiankanoon.org {query}",
        "api_key": SERPAPI_API_KEY,
    }
    url = "https://serpapi.com/search"
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    return resp.json()

@st.cache_data(show_spinner=False)
def fetch_case_html(url: str):
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; Bot/1.0)"
    }
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    return resp.text

def extract_structured_data(html: str):
    soup = BeautifulSoup(html, "html.parser")
    # Look for JSON-LD script tags (application/ld+json)
    jsonld_tags = soup.find_all("script", type="application/ld+json")
    for tag in jsonld_tags:
        try:
            data = json.loads(tag.string)
            # Look for legal case or judgment structured data
            if isinstance(data, dict) and ("@type" in data and "Legal" in data["@type"]):
                return data
            # If multiple items, check list for Legal types
            if isinstance(data, list):
                for entry in data:
                    if isinstance(entry, dict) and ("@type" in entry and "Legal" in entry["@type"]):
                        return entry
        except Exception:
            continue
    # fallback: check for embedded script with window.__INITIAL_STATE__ or similar
    # or try to find structured JSON in scripts
    # Return None if no structured data found
    return None

def extract_judgment_text(html: str):
    # fallback: extract main judgment text by looking for <pre> or main content div
    soup = BeautifulSoup(html, "html.parser")
    # IndiaKanoon often uses <pre id="idText"> or class "document"
    pre = soup.find("pre", id="idText")
    if pre and pre.text.strip():
        return pre.text.strip()
    div = soup.find("div", {"class": "document"})
    if div and div.text.strip():
        return div.text.strip()
    # fallback entire body text (not ideal)
    body = soup.find("body")
    if body:
        return body.get_text(separator="\n").strip()
    return ""

def summarize_text(text: str, model=MODEL_NAME):
    prompt = f"""Summarize the following Indian legal judgment in plain language focusing on facts, issues, reasoning, and conclusion:

{text[:4000]}"""  # limit input length

    try:
        result = subprocess.run(
            ["ollama", "run", model],
            input=prompt.encode(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
        )
        summary = result.stdout.decode().strip()
        if not summary:
            summary = "⚠️ Summarization failed or returned empty output."
        return summary
    except Exception as e:
        return f"❌ Error during summarization: {str(e)}"

# === Streamlit app ===

st.set_page_config(page_title="⚖️ Judgment Summarizer", layout="centered")

st.title("⚖️ Judgment Summarizer")
st.write("Enter a case name (Syntax: X vs Y 2007)")

case_name = st.text_input("Enter Case Name", value="Indian Medical Association vs V.P. Shantha & Ors")

if st.button("Summarize"):
    if not case_name.strip():
        st.error("Please enter a valid case name.")
    else:
        with st.spinner("Searching IndiaKanoon via SerpAPI..."):
            try:
                search_results = serpapi_search(case_name)
            except Exception as e:
                st.error(f"SerpAPI Search failed: {e}")
                st.stop()

            organic = search_results.get("organic_results", [])
            if not organic:
                st.warning("No results found on IndiaKanoon via SerpAPI.")
                st.stop()

            first_result = organic[0]
            case_url = first_result.get("link") or first_result.get("url")
            st.write(f"🔗 [Found case]({case_url})")

            with st.spinner("Fetching case page..."):
                try:
                    case_html = fetch_case_html(case_url)
                except Exception as e:
                    st.error(f"Failed to fetch case page: {e}")
                    st.stop()

            # Try extracting structured data first
            structured = extract_structured_data(case_html)
            if structured:
                st.subheader("📄 Structured Case Data (JSON-LD)")
                st.json(structured)
                # For summary, you can stringify key fields or full JSON as text
                text_to_summarize = json.dumps(structured, indent=2)
            else:
                st.warning("No structured data found, extracting plain judgment text...")
                text_to_summarize = extract_judgment_text(case_html)
                if not text_to_summarize:
                    st.error("No judgment text could be extracted.")
                    st.stop()

            st.subheader("🔍 Raw Text (preview, first 1000 chars)")
            st.text(text_to_summarize[:1000])

            with st.spinner("Generating summary..."):
                summary = summarize_text(text_to_summarize)
                st.subheader("📝 Summary")
                st.write(summary)
