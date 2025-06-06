# app.py

import streamlit as st
from ikapi import IKApi, FileStorage
import subprocess

st.set_page_config(page_title="Judgment Summarizer", layout="wide")
st.title("⚖️ Judgment Summarizer")

# ==============================
# 🔧 Summarizer (Ollama)
# ==============================
def summarize_with_ollama(text, model="gemma3:4b"):
    prompt = f"Summarize the following legal judgment in plain English:\n\n{text[:4000]}"
    try:
        result = subprocess.run(
            ["ollama", "run", model],
            input=prompt.encode(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60
        )
        return result.stdout.decode("utf-8")
    except Exception as e:
        return f"❌ Error during summarization: {str(e)}"

# ==============================
# 📦 Init IK API
# ==============================
@st.cache_resource
def get_ikapi(token: str):
    class Args:
        def __init__(self):
            self.token = token
            self.maxpages = 1
            self.orig = False
            self.fromdate = None
            self.todate = None
            self.sortby = None
    return IKApi(Args(), FileStorage("ik_data"))

# ==============================
# 🔍 Search / Fetch Section
# ==============================
token = st.secrets["ik_token"]
ik = get_ikapi(token)

with st.expander("🔍 Search"):
    query = st.text_input("Enter a case (Syntax: X vs Y 2007)")
    if st.button("Search"):
        if not query.strip():
            st.warning("Please enter a valid search query.")
        else:
            results = ik.search(query)
            if "results" in results:
                for item in results["results"][:5]:  # show top 5
                    st.markdown(f"**{item.get('title')}**\n\n- DocID: `{item.get('docid')}`\n- Snippet: {item.get('snippet')}\n---")
            else:
                st.error("No results found or error in search.")

# ==============================
# 📄 Fetch by DocID
# ==============================
st.subheader("📄 Fetch and Summarize Judgment by DocID")
docid = st.text_input("Enter Document ID from Indian Kanoon")

if st.button("Fetch & Summarize"):
    if not docid.isdigit():
        st.error("Doc ID must be a number.")
    else:
        with st.spinner("Fetching document..."):
            try:
                doc = ik.fetch_doc(int(docid))
                st.success("Fetched successfully.")
                st.markdown(f"### 📝 Title: {doc.get('title', 'Untitled')}")
                st.markdown(f"#### ⚖️ Court: {doc.get('court')} — {doc.get('date')}")
                st.markdown("---")
                st.markdown("### 🧠 Summary:")
                summary = summarize_with_ollama(doc.get("judgmentText", ""))
                st.text_area("Summary", summary, height=300)
            except Exception as e:
                st.error(f"Failed to fetch/summarize: {str(e)}")
