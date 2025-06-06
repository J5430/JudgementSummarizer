import streamlit as st
import requests
from bs4 import BeautifulSoup
import subprocess
import time
import urllib.parse
import re
import os
import json
import hashlib

# ================= LOCAL CACHE PATH ===================
CACHE_DIR = r"C:\Users\jassi\Downloads\judegement sum\cache"

def get_cache_path(query, title, court):
    key = f"{query}|{title}|{court}"
    filename = hashlib.sha256(key.encode()).hexdigest() + ".json"
    return os.path.join(CACHE_DIR, filename)

def load_cached_summary(query, title, court):
    path = get_cache_path(query, title, court)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading cache: {e}")
            return None
    return None

def save_cached_summary(query, title, court, summary):
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)
    path = get_cache_path(query, title, court)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "query": query,
                "title": title,
                "court": court,
                "summary": summary
            }, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving cache: {e}")

# ================= OLLAMA SUMMARIZER ===================
def summarize_with_ollama(prompt, model="gemma3:4b"):
    try:
        result = subprocess.run(
            ["ollama", "run", model],
            input=prompt.encode(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=1800
        )
        if result.returncode != 0:
            return f"⚠️ Ollama error: {result.stderr.decode()}"
        return result.stdout.decode()
    except subprocess.TimeoutExpired:
        return "⚠️ Summarization timed out."
    except Exception as e:
        return f"⚠️ Unexpected error: {str(e)}"

# ================= INDIA KANOON SEARCH ===================
def search_indiakanoon(query, debug=False):
    try:
        url = f"https://indiankanoon.org/search/?formInput={query.replace(' ', '+')}"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=10)

        if debug:
            st.markdown("### 🔍 IndiaKanoon Raw HTML (1000 chars)")
            st.code(res.text[:1000])

        if "No results found" in res.text or "/doc" not in res.text:
            return []

        soup = BeautifulSoup(res.text, "lxml")
        links = []
        for a in soup.select("a[href^='/doc']"):
            href = a['href']
            if href.startswith("/docfragment/"):
                continue
            full = f"https://indiankanoon.org{href}"
            if full not in links:
                links.append(full)
            if len(links) >= 1:
                break
        return links
    except Exception as e:
        if debug:
            st.error(f"IndiaKanoon error: {e}")
        return []

# ================= SERPAPI FALLBACK ===================
def serpapi_fallback_links(query, debug=False):
    try:
        # You need your SerpAPI API key here
        SERPAPI_API_KEY = st.secrets.get("SERPAPI_API_KEY", "")  
        if not SERPAPI_API_KEY:
            if debug:
                st.error("SerpAPI key not configured.")
            return []

        search_url = (
            f"https://serpapi.com/search.json"
            f"?engine=google"
            f"&q=site:indiankanoon.org+{urllib.parse.quote_plus(query)}"
            f"&api_key={SERPAPI_API_KEY}"
        )
        res = requests.get(search_url, timeout=10)

        if debug:
            st.markdown("### 🧭 SerpAPI Raw JSON (5000 chars)")
            st.code(res.text[:5000])

        data = res.json()
        links = []
        for result in data.get("organic_results", []):
            link = result.get("link", "")
            if "indiankanoon.org/doc" in link:
                links.append(link)
            if len(links) >= 1:
                break
        return links
    except Exception as e:
        if debug:
            st.error(f"SerpAPI fallback error: {e}")
        return []

# ================= FETCH CASE DATA ===================
def fetch_structured_case_data(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers)
        soup = BeautifulSoup(res.text, "lxml")

        court = soup.find("h2", class_="docsource_main")
        title = soup.find("h2", class_="doc_title")
        court = court.get_text(strip=True) if court else "Court Not Found"
        title = title.get_text(strip=True) if title else "Title Not Found"

        tags = ["Facts", "Issue", "Section", "CDiscource", "Precedent"]
        data = {tag: [] for tag in tags}
        for tag in tags:
            for p in soup.find_all("p", {"data-structure": tag}):
                txt = p.get_text(strip=True)
                if txt:
                    data[tag].append(txt)

        return court, title, data
    except Exception as e:
        return "Court Not Found", "Title Not Found", {}

# ================= PROMPT GENERATOR ===================
def generate_summary_prompt(court, title, structured_data):
    sections = [f"**Court**: {court}", f"**Title**: {title}"]
    for tag, contents in structured_data.items():
        if contents:
            sections.append(f"**{tag}**:\n" + "\n".join(contents))
    full_text = "\n\n".join(sections)
    return f"""You are a legal analyst. Provide a structured, concise, and formal 5000 word summary of the legal case below. Use simple language suitable for a law student or general audience.

Do not include any follow-up questions or interactive phrases at the end.

Organize the summary using these sections:
1. Facts  
2. Issues  
3. Reasoning  
4. Final Finding  

Focus only on core legal arguments, relevant constitutional provisions, and the court’s conclusion. Avoid unnecessary repetition or commentary.

Case details:

{full_text[:100000]}"""

# ================= STREAMLIT UI ===================
st.set_page_config(page_title="Judgment Summarizer", layout="centered")
st.title("⚖️ Judgment Summarizer")

debug = st.checkbox("Enable Debug Mode")
query = st.text_input("Enter a case (Syntax: X vs Y 2007)")

if st.button("Search & Summarize"):
    if not query:
        st.warning("Please enter a case name.")
    else:
        with st.spinner("Searching India Kanoon..."):
            links = search_indiakanoon(query, debug=debug)

        if not links:
            if debug:
                st.warning("No results from India Kanoon. Trying SerpAPI fallback...")
            links = serpapi_fallback_links(query, debug=debug)

        if not links:
            st.error("❌ No relevant cases found from any source.")
        else:
            for i, link in enumerate(links, 1):
                st.markdown(f"### Casefile")
                st.markdown(f"[🔗 View Full Case →]({link})", unsafe_allow_html=True)

                with st.spinner("Fetching and summarizing..."):
                    court, title, data = fetch_structured_case_data(link)

                    if debug:
                        st.markdown("### 🧠 Debug: Metadata")
                        st.write(f"**Court**: {court}")
                        st.write(f"**Title**: {title}")
                        st.json(data)

                    if not any(data.values()):
                        st.warning("❌ Structured data not found.")
                        continue

                    prompt = generate_summary_prompt(court, title, data)

                    if debug:
                        st.markdown("### 📝 Prompt")
                        st.text_area("Prompt", prompt, height=300)

                    cached = load_cached_summary(query, title, court)
                    if cached and "summary" in cached:
                        summary = cached["summary"]
                    else:
                        summary = summarize_with_ollama(prompt)
                        save_cached_summary(query, title, court, summary)

                    st.markdown(f"**Case Title**: {title}")
                    st.markdown(f"**Court**: {court}")
                    st.text_area("Finding:", summary, height=500, key=f"summary_{i}")
