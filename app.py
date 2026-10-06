import streamlit as st

st.set_page_config(page_title="CX Course Analyzer", layout="wide")

pages = [
    st.Page("analysis_page.py", title="Analysis", icon=":material/analytics:", default=True),
    st.Page("pages/History.py", title="Ride history", icon=":material/history:"),
]

navigation = st.navigation(pages, position="sidebar")
navigation.run()
