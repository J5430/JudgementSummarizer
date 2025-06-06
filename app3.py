import streamlit as st
from ikapi import IKApi, FileStorage
import json
import os

st.set_page_config(page_title="⚖️ Judgment Summarizer", layout="centered")
st.title("⚖️ Judgment Summarizer")

# ==============================
# Load Token and Init API
# ==============================
@st.cache_resource
def get_ikapi():
    class Args:
        def __init__(self):
            self.token = st.secrets["ik_token"]
            self.maxpages = 1
            self.orig = False
            self.fromdate = None
            self.todate = None
            self.sortby = None
    return IKApi(Args(), FileStorage("ik_data"))

ik = get_ikapi()

# ==============================
# Input Search
# ==============================
case_input = st.text_input("Enter a case (e.g., *X vs Y 2007*)")
if not case_input:
    st.info("Please enter a case name to search.")
    st.stop()

# ==============================
# Search India Kanoon API
# ==============================
with st.spinner("Searching Indian Kanoon..."):
    try:
        result = ik.search(case_input)
    except Exception as e:
        st.error(f"Search failed: {e}")
        st.stop()

items = result.get("results", [])
if not items:
    st.warning("No results found.")
    st.stop()

# ==============================
# Display First Result
# ==============================
first = items[0]
docid = first.get("docid")
title = first.get("title")
snippet = first.get("snippet")

case_url = f"https://indiankanoon.org/doc/{docid}/"
st.markdown(f"### 🔗 Found case: [{title}]({case_url})")
st.markdown(f"**Snippet:** {snippet}")
st.divider()

# ==============================
# Fetch Full Judgment by DocID
# ==============================
with st.spinner("Fetching full judgment..."):
    try:
        data = ik.fetch_doc(int(docid))
    except Exception as e:
        st.error(f"Failed to fetch document: {e}")
        st.stop()

# ==============================
# Display Structured Data
# ==============================
st.subheader("📄 Case Metadata")
meta = {
    "Title": data.get("title"),
    "Court": data.get("court"),
    "Date": data.get("date"),
    "Citation": data.get("citation"),
    "URL": case_url
}
st.json(meta)

# ==============================
# Display Raw Judgment (Optional)
# ==============================
with st.expander("🧾 Full Judgment Text"):
    st.text_area("Judgment", data.get("judgmentText", "")[:6000], height=300)
