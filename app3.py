import streamlit as st
import requests
from bs4 import BeautifulSoup
import subprocess
import time
import urllib.parse
import re
import os
import hashlib
import json

# ========== CONFIG ==========
CACHE_DIR = "/mnt/data/legal_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

def get_cache_path(query):
    hash_key = hashlib.sha256(query.encode()).hexdigest()
    return os.path.join(CACHE_DIR, f"{hash_key}.json")

def load_cached_summary(query):
    path = get_cache_path(query)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def save_cached_summary(query, title, court, summary):
    path = get_cache_path(query)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"title": title, "court": court, "summary": summary}, f)

# ========== OLLAMA SUMMARIZER ==========
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

# ========== INDIA KANOON ==========
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

# ========== DUCKDUCKGO FALLBACK ==========
def duckduckgo_fallback_links(query, debug=False):
    try:
        search_query = f"site:indiankanoon.org {query}"
        search_url = f"https://lite.duckduckgo.com/lite/?q={urllib.parse.quote_plus(search_query)}"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(search_url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, "lxml")

        if debug:
            st.markdown("### 🧭 DuckDuckGo Raw HTML (5000 chars)")
            st.code(res.text[:5000])

        links = []
        for a in soup.select("a[href^='http']"):
            href = a.get("href")
            if "indiankanoon.org/doc" in href:
                match = re.search(r"(https?://indiankanoon\.org/doc/\d+)", href)
                if match:
                    links.append(match.group(1))
            if len(links) >= 1:
                break
        return links
    except Exception as e:
        if debug:
            st.error(f"DuckDuckGo fallback error: {e}")
        return []

# ========== CASE STRUCTURE ==========
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

# ========== PROMPT BUILDER ==========
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

{full_text[:50000]}"""

# ========== STREAMLIT UI ==========
st.set_page_config(page_title="Judgment Summarizer", layout="centered")
st.title("⚖️ Judgment Summarizer")

debug = st.checkbox("Enable Debug Mode")
query = st.text_input("Enter a case (Syntax: X vs Y 2007)")

if st.button("Search & Summarize"):
    if not query:
        st.warning("Please enter a case name.")
    else:
        cached = load_cached_summary(query)
        if cached:
            st.success("📦 Loaded from cache!")
            st.markdown(f"**Case Title**: {cached['title']}")
            st.markdown(f"**Court**: {cached['court']}")
            st.text_area("Finding:", cached['summary'], height=500)
        else:
            with st.spinner("Searching India Kanoon..."):
                links = search_indiakanoon(query, debug=debug)

            if not links:
                if debug:
                    st.warning("No results from India Kanoon. Trying DuckDuckGo fallback...")
                links = duckduckgo_fallback_links(query, debug=debug)

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

                        summary = summarize_with_ollama(prompt)

                        if not summary.startswith("⚠️"):
                            save_cached_summary(query, title, court, summary)

                        st.markdown(f"**Case Title**: {title}")
                        st.markdown(f"**Court**: {court}")
                        st.text_area("Finding:", summary, height=500, key=f"summary_{i}")
