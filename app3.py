import streamlit as st
import requests
from bs4 import BeautifulSoup
import subprocess
import time

# ========== OLLAMA SUMMARIZER (with subprocess.run) ==========
def summarize_with_ollama(prompt, model="gemma3:4b"):
    try:
        result = subprocess.run(
            ["ollama", "run", model],
            input=prompt.encode(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=1800  # 30 minutes
        )
        if result.returncode != 0:
            return f"⚠️ Ollama error: {result.stderr.decode()}"
        return result.stdout.decode()
    except subprocess.TimeoutExpired:
        return "⚠️ Summarization timed out."

# ========== INDIA KANOON SCRAPER ==========
def search_indiakanoon(query):
    search_url = f"https://indiankanoon.org/search/?formInput={query.replace(' ', '+')}"
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(search_url, headers=headers)
    soup = BeautifulSoup(res.text, "lxml")

    links = []
    for link in soup.select("a[href^='/doc']"):
        href = link['href']
        if href.startswith("/docfragment/"):
            continue
        full_link = f"https://indiankanoon.org{href}"
        if full_link not in links:
            links.append(full_link)
        if len(links) >= 1:
            break
    return links

def fetch_structured_case_data(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(url, headers=headers)
    soup = BeautifulSoup(res.text, "lxml")

    court = soup.find("h2", class_="docsource_main")
    title = soup.find("h2", class_="doc_title")

    court = court.get_text(strip=True) if court else "Court Not Found"
    title = title.get_text(strip=True) if title else "Title Not Found"

    structured_tags = ["Facts", "Issue", "Section", "CDiscource", "Precedent"]
    data = {tag: [] for tag in structured_tags}

    for tag in structured_tags:
        for p in soup.find_all("p", {"data-structure": tag}):
            text = p.get_text(strip=True)
            if text:
                data[tag].append(text)

    return court, title, data

def generate_summary_prompt(court, title, structured_data):
    summary_sections = [f"**Court**: {court}", f"**Title**: {title}"]
    for tag, contents in structured_data.items():
        if contents:
            joined = "\n".join(contents)
            summary_sections.append(f"**{tag}**:\n{joined}")
    combined_text = "\n\n".join(summary_sections)
    return f"""You are a legal analyst. Provide a structured, concise, and formal 5000 word summary of the legal case below. Use simple language suitable for a law student or general audience. 

Do not include any follow-up questions or interactive phrases at the end.

Organize the summary using these sections:
1. Facts  
2. Issues  
3. Reasoning  
4. Final Finding  

Focus only on core legal arguments, relevant constitutional provisions, and the court’s conclusion. Avoid unnecessary repetition or commentary.

Case details:

{combined_text[:50000]}"""


# ========== STREAMLIT UI ==========
st.set_page_config(page_title="Judgment Summarizer", layout="centered")
st.title("⚖️ Judgment Summarizer")

debug = st.checkbox("Enable Debug Mode")

query = st.text_input("Enter a case (Syntax: X vs Y 2007)")

if st.button("Search & Summarize"):
    if not query:
        st.warning("Please enter a case name.")
    else:
        with st.spinner("Searching India Kanoon..."):
            links = search_indiakanoon(query)

        if debug:
            st.markdown("### 🔍 Debug: Search Results")
            st.write(links)

        if not links:
            st.error("No relevant cases found.")
        else:
            for i, link in enumerate(links, 1):
                st.markdown(f"### Casefile")
                st.markdown(f"[View Full Case →]({link})", unsafe_allow_html=True)

                with st.spinner("Fetching and summarizing..."):
                    court, title, data = fetch_structured_case_data(link)

                    if debug:
                        st.markdown("### 🧠 Debug: Fetched Metadata")
                        st.write(f"**Court**: {court}")
                        st.write(f"**Title**: {title}")
                        st.write("**Structured Data**:")
                        st.json(data)

                    if not any(data.values()):
                        st.warning("❌ Structured data not found.")
                        continue

                    prompt = generate_summary_prompt(court, title, data)

                    if debug:
                        st.markdown("### 📄 Debug: Generated Prompt")
                        st.text_area("Prompt Preview", prompt, height=300, key=f"prompt_{i}")

                    summary = summarize_with_ollama(prompt)

                    if debug and summary.startswith("⚠️"):
                        st.markdown("### ⚠️ Debug: LLM Response Error")
                        st.error(summary)

                    st.markdown(f"**Case Title**: {title}")
                    st.markdown(f"**Court**: {court}")
                    st.text_area("Finding:", summary, height=500, key=f"summary_{i}")
