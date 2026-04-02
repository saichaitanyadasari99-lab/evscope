from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components


st.set_page_config(page_title="EVScope Dashboard", layout="wide")

html_path = Path(__file__).with_name("EVScope_Dashboard_fixed.html")

st.markdown(
    """
    <style>
      html, body, [data-testid="stAppViewContainer"], .stApp { margin: 0; padding: 0; background: #070b13; }
      [data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"] { display: none !important; }
      [data-testid="stMain"] > div { padding: 0 !important; }
      .block-container {
        max-width: 100vw !important;
        padding: 0 !important;
        margin: 0 !important;
      }
      [data-testid="stVerticalBlock"] { gap: 0 !important; }
      iframe {
        width: 100vw !important;
        min-height: 100vh !important;
        border: 0 !important;
        border-radius: 0 !important;
        display: block !important;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

if not html_path.exists():
    st.error(f"Missing HTML file: {html_path}")
    st.stop()

html = html_path.read_text(encoding="utf-8", errors="ignore")
components.html(html, height=2400, scrolling=True)
