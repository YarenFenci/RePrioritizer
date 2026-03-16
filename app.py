"""
STP Analyzer — BiP QA
Tab 1: Defined Scenario PreReview    → manuel senaryo girişi, priority ata
Tab 2: Exploratory RePrioritizer     → CSV yükle (summary+desc), priority yeniden değerlendir
"""
 
import io
import re
import sys
from pathlib import Path
from typing import List, Tuple, Optional
 
import pandas as pd
import streamlit as st
 
sys.path.insert(0, str(Path(__file__).parent))
from stp_engine import (
    decide_priority,
    detect_device_os_scope,
    PRIORITY_ORDER,
    REASON_MAP,
    GATING_TERMS, HIGH_TERMS, MEDIUM_TERMS,
    LOW_COSMETIC_TERMS, HARD_CRASH_TERMS, FREEZE_TERMS,
    FREQ_OPTIONS,
)
 
# ═══════════════════════════════════════════════════════════════
# Shared metadata
# ═══════════════════════════════════════════════════════════════
 
PRIORITY_META = {
    "Gating": {
        "color": "#E53935", "bg": "#FFF0F0", "border": "#FFCDD2",
        "icon": "🔴", "label": "GATING",
        "desc": "Blocks release — core function broken or reproducible crash.",
    },
    "High": {
        "color": "#FB8C00", "bg": "#FFF8F0", "border": "#FFE0B2",
        "icon": "🟠", "label": "HIGH",
        "desc": "Important feature affected — fix within 2 weeks.",
    },
    "Medium": {
        "color": "#1E88E5", "bg": "#F0F6FF", "border": "#BBDEFB",
        "icon": "🔵", "label": "MEDIUM",
        "desc": "Secondary UX issue — workaround exists, fix within 6 weeks.",
    },
    "Low": {
        "color": "#43A047", "bg": "#F0FFF0", "border": "#C8E6C9",
        "icon": "🟢", "label": "LOW",
        "desc": "Cosmetic / minor edge case — no functional impact.",
    },
}
 
PRIORITY_COLORS = {p: m["color"] for p, m in PRIORITY_META.items()}
 
FREQ_META = {
    "always":       {"icon": "🔁", "color": "#E53935", "label": "Always"},
    "frequently":   {"icon": "🔄", "color": "#FB8C00", "label": "Frequently"},
    "occasionally": {"icon": "🔃", "color": "#1E88E5", "label": "Occasionally"},
    "rarely":       {"icon": "🔀", "color": "#43A047", "label": "Rarely"},
    "once":         {"icon": "1️⃣",  "color": "#78909C", "label": "Once"},
}
 
 
# ═══════════════════════════════════════════════════════════════
# Description parser  (Tab 2)
# ═══════════════════════════════════════════════════════════════
 
def parse_description(desc: str) -> dict:
    """
    Jira Description alanını ayrıştır.
    Crashlytics log mu, bug report mu ayırt et.
    Bug report ise steps / actual / expected çıkar.
    """
    if not desc or not desc.strip():
        return {"type": "empty"}
 
    d = desc.strip()
 
    # Crashlytics / Firebase log dump
    if re.search(r'console\.firebase\.google\.com', d):
        return {"type": "crashlytics_log", "raw": d[:600]}
 
    parts = {"type": "bug_report", "raw": d}
 
    # Steps
    m = re.search(
        r'(?:steps?\s*(?:to\s*)?reproduce|test\s*steps?)\s*[:\n]+(.*?)'
        r'(?=\n\s*(?:actual|expected|precondition|logs?|tr\s*:|en\s*:|$))',
        d, re.IGNORECASE | re.DOTALL
    )
    if m:
        parts["steps"] = _clean_jira(m.group(1))
 
    # Actual result
    m = re.search(
        r'actual\s*result\s*[:\n]+(.*?)'
        r'(?=\n\s*(?:expected|steps?|precondition|logs?|tr\s*:|en\s*:|$))',
        d, re.IGNORECASE | re.DOTALL
    )
    if m:
        parts["actual"] = _clean_jira(m.group(1))
 
    # Expected result
    m = re.search(
        r'expected\s*result\s*[:\n]+(.*?)'
        r'(?=\n\s*(?:actual|steps?|precondition|logs?|tr\s*:|en\s*:|$))',
        d, re.IGNORECASE | re.DOTALL
    )
    if m:
        parts["expected"] = _clean_jira(m.group(1))
 
    return parts
 
 
def _clean_jira(text: str) -> str:
    """Jira markup temizle, boşlukları normalize et."""
    t = re.sub(r'\*+', '', text)
    t = re.sub(r'h[123]\.\s*', '', t)
    t = re.sub(r'\[.*?\]', '', t)
    t = re.sub(r'!\S+!', '', t)
    t = re.sub(r'#\s*', '', t)
    t = re.sub(r'\xa0', ' ', t)
    t = re.sub(r'\n{3,}', '\n\n', t)
    return t.strip()[:400]
 
 
# ═══════════════════════════════════════════════════════════════
# Reprioritizer engine  (Tab 2)
# ═══════════════════════════════════════════════════════════════
 
def reprioritize_row(summary: str, desc: str, current_priority: str) -> dict:
    """
    Tek satır için priority kararı ver.
    Description'dan steps/actual/expected çıkararak stp_engine'e besler.
    """
    desc_parts = parse_description(desc)
 
    # Crashlytics log → summary'de "Crashlytics" prefix varsa log dump, mevcut priority koru
    if desc_parts["type"] == "crashlytics_log":
        is_log_only = bool(re.match(r'^crashlytics\s*[-|]', summary.lower()))
        if is_log_only:
            note = "Crashlytics log dump — priority mevcut atamadan alındı, manuel inceleme önerilir."
            return {
                "stp_priority":       current_priority or "Medium",
                "is_scoped":          False,
                "scope_type":         "",
                "scope_detail":       "",
                "reason":             note,
                "adjusted_note":      "",
                "desc_type":          "crashlytics_log",
                "extracted_steps":    "",
                "extracted_actual":   "",
                "extracted_expected": "",
            }
 
    steps    = desc_parts.get("steps", "")
    actual   = desc_parts.get("actual", "")
    expected = desc_parts.get("expected", "")
 
    priority, is_scoped, scope_type, scope_detail, reason, adjusted_note = decide_priority(
        text="",
        actual_result=actual,
        expected_result=expected,
        summary=summary,
        steps=steps,
        reproduce_frequency="always",
        device_scope="",
    )
 
    return {
        "stp_priority":       priority,
        "is_scoped":          is_scoped,
        "scope_type":         scope_type,
        "scope_detail":       scope_detail,
        "reason":             reason,
        "adjusted_note":      adjusted_note,
        "desc_type":          desc_parts["type"],
        "extracted_steps":    steps[:120],
        "extracted_actual":   actual[:120],
        "extracted_expected": expected[:120],
    }
 
 
# ═══════════════════════════════════════════════════════════════
# CSV loader  (Tab 2)
# ═══════════════════════════════════════════════════════════════
 
REPRIO_COLS = {
    "Issue key":   "Issue Key",
    "Priority":    "Current Priority",
    "Summary":     "Summary",
    "Description": "Description",
}
 
 
def load_reprio_csv(uploaded_file) -> Tuple[pd.DataFrame, str]:
    content = uploaded_file.read()
    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="replace")
 
    df = None
    for sep in (";", ",", "\t"):
        try:
            tmp = pd.read_csv(io.StringIO(content), sep=sep, engine="python",
                              on_bad_lines="skip")
            if len(tmp.columns) > 2:
                df = tmp
                break
        except Exception:
            continue
 
    if df is None:
        raise ValueError("CSV okunamadı.")
 
    missing = [c for c in REPRIO_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Eksik kolonlar: {missing}")
 
    df = df[[c for c in REPRIO_COLS]].rename(columns=REPRIO_COLS).copy()
    df["Current Priority"] = (
        df["Current Priority"].fillna("").astype(str).str.strip().str.capitalize()
    )
    df["Summary"]     = df["Summary"].fillna("").astype(str).str.strip()
    df["Description"] = df["Description"].fillna("").astype(str).str.strip()
    return df, uploaded_file.name
 
 
def run_reprioritizer(df: pd.DataFrame) -> pd.DataFrame:
    results = []
    for _, row in df.iterrows():
        r = reprioritize_row(row["Summary"], row["Description"], row["Current Priority"])
        results.append(r)
 
    out = df.copy()
    out["STP Priority"]        = [r["stp_priority"]        for r in results]
    out["Changed"]             = out["Current Priority"] != out["STP Priority"]
    out["Desc Type"]           = [r["desc_type"]           for r in results]
    out["Extracted Steps"]     = [r["extracted_steps"]     for r in results]
    out["Extracted Actual"]    = [r["extracted_actual"]    for r in results]
    out["Extracted Expected"]  = [r["extracted_expected"]  for r in results]
    out["Reason"]              = [r["reason"]              for r in results]
    out["Scope Detail"]        = [r["scope_detail"]        for r in results]
    return out
 
 
# ═══════════════════════════════════════════════════════════════
# CSS
# ═══════════════════════════════════════════════════════════════
 
def inject_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Inter:wght@300;400;500;600;700&family=Syne:wght@700;800&display=swap');
 
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .stApp { background: #F4F6FA; }
    .block-container { padding-top: 1rem !important; max-width: 1300px !important; }
 
    /* ── Header ── */
    .stp-header { padding: 1.6rem 0 0.8rem 0; }
    .stp-title {
        font-family: 'Syne', sans-serif; font-size: 1.9rem; font-weight: 800;
        color: #1A2340; letter-spacing: -0.03em; line-height: 1.1; margin: 0;
    }
    .stp-title span { color: #1976D2; }
    .stp-subtitle { font-size: 0.82rem; color: #6B7A99; margin-top: 0.4rem; }
    .stp-divider {
        height: 2px;
        background: linear-gradient(90deg, #1976D2 0%, #90CAF9 60%, transparent 100%);
        margin: 0.8rem 0 0.5rem 0;
    }
 
    /* ── Labels ── */
    .form-label {
        font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; font-weight: 600;
        color: #1976D2; letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 0.4rem;
    }
    .section-label {
        font-family: 'JetBrains Mono', monospace; font-size: 0.65rem; font-weight: 600;
        color: #7890B0; letter-spacing: 0.1em; text-transform: uppercase;
        margin: 0.8rem 0 0.3rem 0;
    }
 
    /* ── Inputs ── */
    .stTextInput input, .stTextArea textarea {
        background: #FFFFFF !important; border: 1.5px solid #D0D9E8 !important;
        border-radius: 8px !important; color: #1A2340 !important;
        font-family: 'Inter', sans-serif !important; font-size: 0.88rem !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05) !important;
    }
    .stTextInput input:focus, .stTextArea textarea:focus {
        border-color: #1976D2 !important;
        box-shadow: 0 0 0 3px rgba(25,118,210,0.1) !important;
    }
    .stTextInput input::placeholder, .stTextArea textarea::placeholder {
        color: #A8B8CC !important;
    }
    .stSelectbox > div > div {
        background: #FFFFFF !important; border: 1.5px solid #D0D9E8 !important;
        border-radius: 8px !important; color: #1A2340 !important;
    }
 
    /* ── Button ── */
    .stButton > button {
        background: linear-gradient(135deg, #1976D2, #1565C0) !important;
        color: #FFFFFF !important; border: none !important; border-radius: 8px !important;
        font-family: 'Inter', sans-serif !important; font-weight: 600 !important;
        font-size: 0.9rem !important; width: 100% !important;
        box-shadow: 0 2px 8px rgba(25,118,210,0.3) !important;
        transition: all 0.2s !important;
    }
    .stButton > button:hover {
        background: linear-gradient(135deg, #1E88E5, #1976D2) !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 12px rgba(25,118,210,0.4) !important;
    }
 
    /* ── Tabs ── */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px; background: #EEF2F8 !important;
        border-bottom: 2px solid #D0D9E8 !important;
        border-radius: 8px 8px 0 0; padding: 4px 4px 0 4px;
    }
    .stTabs [data-baseweb="tab"] {
        font-family: 'JetBrains Mono', monospace !important; font-size: 0.72rem !important;
        color: #7890B0 !important; padding: 0.5rem 1.2rem !important;
        border-radius: 6px 6px 0 0 !important; background: transparent !important;
    }
    .stTabs [aria-selected="true"] {
        color: #1976D2 !important; background: #FFFFFF !important;
        border-bottom: 2px solid #1976D2 !important; font-weight: 600 !important;
    }
 
    /* ── Result card (Tab 1) ── */
    .result-card { border-radius: 12px; padding: 1.4rem; margin-bottom: 1rem; border: 1.5px solid; }
    .result-priority-label {
        font-family: 'JetBrains Mono', monospace; font-size: 0.65rem; font-weight: 600;
        letter-spacing: 0.15em; text-transform: uppercase; margin-bottom: 0.3rem;
    }
    .result-priority-value {
        font-family: 'Syne', sans-serif; font-size: 2rem; font-weight: 800;
        letter-spacing: -0.02em; line-height: 1; margin-bottom: 0.4rem;
    }
    .result-desc { font-size: 0.82rem; opacity: 0.8; line-height: 1.4; }
 
    /* ── Reason / info boxes ── */
    .reason-box {
        background: #FFFFFF; border: 1.5px solid #D0D9E8;
        border-left: 4px solid #1976D2;
        border-radius: 8px; padding: 1rem 1.2rem; margin-top: 0.8rem;
        box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    }
    .reason-title {
        font-family: 'JetBrains Mono', monospace; font-size: 0.65rem; color: #1976D2;
        letter-spacing: 0.12em; text-transform: uppercase; margin-bottom: 0.4rem;
    }
    .reason-text { font-size: 0.83rem; color: #3A4A6B; line-height: 1.6; }
 
    .adjust-box {
        background: #EBF3FD; border: 1.5px solid #90CAF9; border-radius: 8px;
        padding: 0.8rem 1rem; margin-top: 0.8rem; font-size: 0.82rem; line-height: 1.6;
        color: #1A4A7A;
    }
    .adjust-box-label {
        font-family: 'JetBrains Mono', monospace; font-size: 0.6rem; letter-spacing: 0.12em;
        text-transform: uppercase; margin-bottom: 0.3rem; font-weight: 600; color: #1976D2;
    }
 
    /* ── Keyword chips ── */
    .keyword-box {
        background: #FFFFFF; border: 1.5px solid #D0D9E8; border-radius: 8px;
        padding: 0.8rem 1.1rem; margin-top: 0.8rem;
        box-shadow: 0 1px 4px rgba(0,0,0,0.05);
    }
    .kw-chip {
        display: inline-block; background: #EEF2F8; border: 1px solid #C5D0E0;
        border-radius: 4px; padding: 2px 8px; font-family: 'JetBrains Mono', monospace;
        font-size: 0.68rem; color: #3A5A8A; margin: 2px 3px;
    }
 
    /* ── Compare boxes ── */
    .cmp-box {
        background: #FFFFFF; border: 1.5px solid #D0D9E8; border-radius: 8px;
        padding: 0.8rem 1rem; margin-top: 0.5rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .cmp-label {
        font-family: 'JetBrains Mono', monospace; font-size: 0.6rem; letter-spacing: 0.1em;
        text-transform: uppercase; margin-bottom: 0.3rem;
    }
    .cmp-text { font-size: 0.82rem; color: #3A4A6B; line-height: 1.5; }
 
    /* ── Stat boxes ── */
    .stat-box {
        background: #FFFFFF; border: 1.5px solid #D0D9E8; border-radius: 10px;
        padding: 0.9rem 1rem; text-align: center;
        box-shadow: 0 2px 6px rgba(0,0,0,0.06);
    }
    .stat-num {
        font-family: 'JetBrains Mono', monospace; font-size: 1.5rem; font-weight: 700;
    }
    .stat-label { font-size: 0.7rem; color: #7890B0; margin-top: 3px; font-weight: 500; }
 
    /* ── Priority badge ── */
    .p-badge {
        display: inline-block; padding: 2px 10px; border-radius: 4px;
        font-family: 'JetBrains Mono', monospace; font-size: 0.7rem;
        font-weight: 700; color: #fff; letter-spacing: 0.04em;
    }
 
    /* ── History rows ── */
    .hist-row {
        display: flex; align-items: center; gap: 10px; padding: 0.6rem 0.9rem;
        border-radius: 8px; background: #FFFFFF; border: 1.5px solid #D0D9E8;
        margin-bottom: 6px; font-size: 0.82rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .hist-key { font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; color: #1976D2; min-width: 36px; font-weight: 600; }
    .hist-summary { flex: 1; color: #5A6A8A; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .hist-badge {
        font-family: 'JetBrains Mono', monospace; font-size: 0.68rem; font-weight: 700;
        padding: 2px 9px; border-radius: 4px; color: #fff; white-space: nowrap;
    }
 
    /* ── Reprio cards ── */
    .reprio-card {
        background: #FFFFFF; border: 1.5px solid #D0D9E8; border-radius: 10px;
        padding: 0.9rem 1.1rem; margin-bottom: 0.5rem;
        box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    }
    .reprio-header { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 0.4rem; }
    .reprio-key { font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; color: #1976D2; font-weight: 700; }
    .reprio-summary { font-size: 0.82rem; color: #3A4A6B; margin-bottom: 0.3rem; }
    .reprio-reason { font-size: 0.72rem; color: #7890B0; font-style: italic; padding-left: 0.6rem; border-left: 2px solid #D0D9E8; }
    .arrow { color: #1976D2; font-weight: 700; }
    .desc-type-badge {
        font-family: 'JetBrains Mono', monospace; font-size: 0.62rem; padding: 1px 7px;
        border-radius: 10px; font-weight: 600;
    }
 
    /* ── Streamlit overrides ── */
    div[data-testid="stFileUploader"] {
        border: 1.5px solid #D0D9E8 !important; border-radius: 8px !important;
        background: #FFFFFF !important;
    }
    div[data-testid="stDataFrame"] { border: 1.5px solid #D0D9E8; border-radius: 8px; }
    section[data-testid="stSidebar"] {
        background: #EEF2F8 !important; border-right: 1.5px solid #D0D9E8 !important;
    }
    /* Expander styling */
    details { background: #FFFFFF !important; border: 1.5px solid #D0D9E8 !important; border-radius: 8px !important; margin-bottom: 6px !important; }
    details summary { color: #EEF2F8 !important; font-size: 0.84rem !important; font-weight: 500 !important; }
    details summary:hover { background: #F0F4FA !important; }
 
    #MainMenu, footer, header { visibility: hidden; }
    </style>
    """, unsafe_allow_html=True)
 
 
# ═══════════════════════════════════════════════════════════════
# Shared helpers
# ═══════════════════════════════════════════════════════════════
 
def priority_badge(p: str) -> str:
    col = PRIORITY_COLORS.get(p, "#78909C")
    return f'<span class="p-badge" style="background:{col}">{p}</span>'
 
 
def find_hit_keywords(text: str, priority: str) -> List[str]:
    t = text.lower()
    pool = {
        "Gating": GATING_TERMS + HARD_CRASH_TERMS,
        "High":   HIGH_TERMS,
        "Medium": MEDIUM_TERMS,
        "Low":    LOW_COSMETIC_TERMS,
    }.get(priority, [])
    return [kw for kw in pool if kw and kw in t][:8]
 
 
def auto_detect_device(text: str) -> str:
    _, _, scope_detail = detect_device_os_scope(text)
    return scope_detail or ""
 
 
# ═══════════════════════════════════════════════════════════════
# Tab 1 — Defined Scenario PreReview
# ═══════════════════════════════════════════════════════════════
 
def render_prereview_result(summary, steps, actual, expected, freq, device_scope):
    priority, is_scoped, scope_type, scope_detail, reason, adjusted_note = decide_priority(
        text="",
        actual_result=actual,
        expected_result=expected,
        summary=summary,
        steps=steps,
        reproduce_frequency=freq,
        device_scope=device_scope,
    )
    meta = PRIORITY_META[priority]
    hits = find_hit_keywords(
        (summary + " " + steps + " " + actual + " " + expected).lower(), priority
    )
 
    st.markdown(f"""
    <div class="result-card" style="background:{meta['bg']};border-color:{meta['border']};">
        <div class="result-priority-label" style="color:{meta['color']}">STP PRIORITY</div>
        <div class="result-priority-value" style="color:{meta['color']}">{meta['icon']} {meta['label']}</div>
        <div class="result-desc" style="color:{meta['color']}">{meta['desc']}</div>
    </div>
    """, unsafe_allow_html=True)
 
    if adjusted_note.strip():
        st.markdown(f"""
        <div class="adjust-box">
            <div class="adjust-box-label">Priority Adjustments Applied</div>
            <div style="color:#A8C8E8">{adjusted_note}</div>
        </div>
        """, unsafe_allow_html=True)
 
    if actual.strip() or expected.strip():
        col_a, col_e = st.columns(2)
        with col_a:
            st.markdown(f"""
            <div class="cmp-box">
                <div class="cmp-label" style="color:#E53935">🔴 Actual Result</div>
                <div class="cmp-text">{actual.strip() or '<em style="opacity:0.4">Not specified</em>'}</div>
            </div>""", unsafe_allow_html=True)
        with col_e:
            st.markdown(f"""
            <div class="cmp-box">
                <div class="cmp-label" style="color:#43A047">🟢 Expected Result</div>
                <div class="cmp-text">{expected.strip() or '<em style="opacity:0.4">Not specified</em>'}</div>
            </div>""", unsafe_allow_html=True)
 
    st.markdown(f"""
    <div class="reason-box">
        <div class="reason-title">Why this priority?</div>
        <div class="reason-text">{reason}</div>
    </div>
    """, unsafe_allow_html=True)
 
    if hits:
        chips = "".join(f'<span class="kw-chip">{kw}</span>' for kw in hits)
        st.markdown(f"""
        <div class="keyword-box">
            <div class="reason-title" style="margin-bottom:0.4rem">Matched signals</div>
            {chips}
        </div>
        """, unsafe_allow_html=True)
 
    return priority, is_scoped, scope_type, scope_detail, reason, adjusted_note
 
 
def tab_prereview():
    if "history" not in st.session_state:
        st.session_state.history = []
 
    left, right = st.columns([1, 1], gap="large")
 
    with left:
        st.markdown('<div class="form-label">Scenario Input</div>', unsafe_allow_html=True)
 
        summary = st.text_input(
            "Summary",
            placeholder="e.g. App crashes while sending voice message (Redmi 10)",
            label_visibility="collapsed",
            key="pre_summary_v3",
        )
 
        st.markdown('<div class="section-label">Steps to Reproduce</div>', unsafe_allow_html=True)
        steps = st.text_area(
            "Steps",
            placeholder="1. Open chat\n2. Tap voice message\n3. Record and send\n4. App force closes",
            height=100, label_visibility="collapsed", key="pre_steps_v3",
        )
 
        col_a, col_e = st.columns(2)
        with col_a:
            st.markdown('<div class="section-label">🔴 Actual Result</div>', unsafe_allow_html=True)
            actual = st.text_area(
                "Actual", placeholder="What happens?",
                height=90, label_visibility="collapsed", key="pre_actual_v3",
            )
        with col_e:
            st.markdown('<div class="section-label">🟢 Expected Result</div>', unsafe_allow_html=True)
            expected = st.text_area(
                "Expected", placeholder="What should happen?",
                height=90, label_visibility="collapsed", key="pre_expected_v3",
            )
 
        col_f, col_d = st.columns(2)
        with col_f:
            st.markdown('<div class="section-label">🔁 Reproduce Frequency</div>', unsafe_allow_html=True)
            freq_labels = {
                "always": "🔁 Always", "frequently": "🔄 Frequently",
                "occasionally": "🔃 Occasionally", "rarely": "🔀 Rarely", "once": "1️⃣ Once",
            }
            freq_display = list(freq_labels.values())
            freq_keys    = list(freq_labels.keys())
            sel = st.selectbox("Freq", freq_display, index=0,
                               label_visibility="collapsed", key="pre_freq_v3")
            freq = freq_keys[freq_display.index(sel)]
 
        with col_d:
            st.markdown('<div class="section-label">📱 Device / OS Scope</div>', unsafe_allow_html=True)
            live = (st.session_state.get("pre_summary_v3", "") + " " +
                    st.session_state.get("pre_steps_v3", ""))
            auto_dev = auto_detect_device(live)
            device_scope = st.text_input(
                "Device", value=auto_dev,
                placeholder="e.g. Samsung A5, iOS 16…",
                label_visibility="collapsed", key="pre_device_v3",
            )
            if auto_dev and auto_dev.lower() == device_scope.strip().lower():
                st.markdown('<div style="font-size:0.7rem;color:#FF9800;margin-top:3px">⚡ Auto-detected</div>', unsafe_allow_html=True)
            elif device_scope.strip():
                st.markdown('<div style="font-size:0.7rem;color:#43A047;margin-top:3px">✏️ Manually set</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div style="font-size:0.7rem;color:#3A4A6B;margin-top:3px">Leave empty = all devices</div>', unsafe_allow_html=True)
 
        st.markdown("<br>", unsafe_allow_html=True)
        analyze = st.button("▶  Analyze Priority", key="pre_analyze_v3")
 
        # Legend
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="form-label" style="color:#3A4A6B;margin-bottom:0.6rem">Priority Reference</div>',
                    unsafe_allow_html=True)
        for p, m in PRIORITY_META.items():
            st.markdown(
                f'<div style="display:flex;align-items:flex-start;gap:8px;margin-bottom:6px">'
                f'<span style="width:10px;height:10px;border-radius:50%;background:{m["color"]};'
                f'display:inline-block;flex-shrink:0;margin-top:3px"></span>'
                f'<div><span style="font-family:\'JetBrains Mono\',monospace;font-size:0.7rem;'
                f'color:{m["color"]};font-weight:600">{p}</span>'
                f'<span style="font-size:0.75rem;color:#3A4A6B;display:block;margin-top:1px">'
                f'{m["desc"]}</span></div></div>',
                unsafe_allow_html=True,
            )
 
        st.markdown("""
        <div style="background:#FFFFFF;border:1px solid #D0D9E8;border-left:3px solid #E53935;
                    border-radius:8px;padding:0.8rem 1rem;margin-top:1rem">
            <div style="font-family:'JetBrains Mono',monospace;font-size:0.6rem;color:#E53935;
                        letter-spacing:0.1em;text-transform:uppercase;margin-bottom:0.4rem">
                Gating Criteria (BiP)
            </div>
            <div style="font-size:0.76rem;color:#6B7A99;line-height:1.7">
                • Messaging / calling / login completely broken<br>
                • Always or scenario-specific reproducible crash<br>
                • Fraud / financial loss risk<br>
                • Permanent data loss<br>
                • Only core flow — not every minor crash is Gating
            </div>
        </div>
        """, unsafe_allow_html=True)
 
    with right:
        if analyze:
            if not summary.strip():
                st.warning("Please enter at least a summary.")
            else:
                priority, is_scoped, scope_type, scope_detail, reason, adjusted_note = \
                    render_prereview_result(summary, steps, actual, expected, freq, device_scope)
                st.session_state.history.append({
                    "summary": summary, "steps": steps, "actual": actual,
                    "expected": expected, "freq": freq, "device_scope": device_scope,
                    "priority": priority, "is_scoped": is_scoped,
                    "scope_type": scope_type, "scope_detail": scope_detail,
                    "reason": reason, "adjusted_note": adjusted_note,
                })
        else:
            st.markdown("""
            <div style="height:220px;border:1px dashed #D0D9E8;border-radius:12px;
                display:flex;flex-direction:column;align-items:center;justify-content:center;
                color:#B0BED0;font-family:'JetBrains Mono',monospace;font-size:0.8rem;
                letter-spacing:0.06em;gap:8px">
                <div style="font-size:2rem">🎯</div>
                <div>PRIORITY RESULT WILL APPEAR HERE</div>
                <div style="font-size:0.68rem;opacity:0.5">Fill in the scenario and click Analyze</div>
            </div>
            """, unsafe_allow_html=True)
 
    # Session history
    if st.session_state.get("history"):
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(
            f'<div class="form-label" style="color:#6B7A99;margin-bottom:0.6rem">'
            f'SESSION HISTORY &nbsp;·&nbsp; {len(st.session_state.history)} scenarios</div>',
            unsafe_allow_html=True,
        )
        for i, entry in enumerate(reversed(st.session_state.history)):
            m  = PRIORITY_META[entry["priority"]]
            fm = FREQ_META.get(entry.get("freq", "always"), FREQ_META["always"])
            st.markdown(f"""
            <div class="hist-row">
                <span class="hist-key">#{len(st.session_state.history)-i}</span>
                <span class="hist-summary">{entry['summary'][:60]}{'…' if len(entry['summary'])>60 else ''}</span>
                <span style="font-size:0.68rem;color:{fm['color']};font-family:'JetBrains Mono',monospace">
                    {fm['icon']} {fm['label']}</span>
                <span class="hist-badge" style="background:{m['color']}">{m['label']}</span>
            </div>
            """, unsafe_allow_html=True)
 
        hist_df = pd.DataFrame(st.session_state.history)
        st.download_button(
            "⬇ Export session as CSV",
            data=hist_df.to_csv(index=False).encode("utf-8"),
            file_name="stp_session.csv", mime="text/csv",
            key=f"dl_pre_v3_{len(st.session_state.history)}",
        )
 
 
# ═══════════════════════════════════════════════════════════════
# Tab 2 — Exploratory RePrioritizer
# ═══════════════════════════════════════════════════════════════
 
def render_reprio_summary_stats(out_df: pd.DataFrame):
    n_total   = len(out_df)
    n_changed = int(out_df["Changed"].sum())
 
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    for col, num, label, color in [
        (c1, n_total,   "Toplam Issue",     "#4FC3F7"),
        (c2, n_changed, "Priority Degisti", "#FB8C00"),
        (c3, int(out_df["STP Priority"].eq("Gating").sum()), "Gating",  "#E53935"),
        (c4, int(out_df["STP Priority"].eq("High").sum()),   "High",    "#FB8C00"),
        (c5, int(out_df["STP Priority"].eq("Medium").sum()), "Medium",  "#1E88E5"),
        (c6, int(out_df["STP Priority"].eq("Low").sum()),    "Low",     "#43A047"),
    ]:
        col.markdown(
            f'<div class="stat-box"><div class="stat-num" style="color:{color}">{num}</div>'
            f'<div class="stat-label">{label}</div></div>',
            unsafe_allow_html=True,
        )
 
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
 
    rows_html = ""
    for p in ["Gating", "High", "Medium", "Low"]:
        cur_count = int((out_df["Current Priority"] == p).sum())
        stp_count = int((out_df["STP Priority"] == p).sum())
        delta     = stp_count - cur_count
        col_color = PRIORITY_COLORS.get(p, "#78909C")
        if delta > 0:
            delta_html = f'<span style="color:#E53935;font-weight:700;font-family:monospace">+{delta}</span>'
        elif delta < 0:
            delta_html = f'<span style="color:#43A047;font-weight:700;font-family:monospace">{delta}</span>'
        else:
            delta_html = '<span style="color:#3A4A6B">—</span>'
        rows_html += (
            f'<tr>'
            f'<td style="padding:8px 14px"><span class="p-badge" style="background:{col_color}">{p}</span></td>'
            f'<td style="padding:8px 14px;text-align:center;font-family:monospace;color:#5A6A8A">{cur_count}</td>'
            f'<td style="padding:8px 14px;text-align:center;font-family:monospace;color:#1A2340;font-weight:600">{stp_count}</td>'
            f'<td style="padding:8px 14px;text-align:center">{delta_html}</td>'
            f'</tr>'
        )
 
    st.markdown(
        f'<table style="width:100%;border-collapse:collapse;background:#FFFFFF;'
        f'border:1px solid #D0D9E8;border-radius:8px;overflow:hidden">'
        f'<thead><tr style="border-bottom:1px solid #D0D9E8">'
        f'<th style="padding:8px 14px;text-align:left;font-family:monospace;font-size:0.65rem;color:#5A6A8A;letter-spacing:0.1em;text-transform:uppercase">Priority</th>'
        f'<th style="padding:8px 14px;text-align:center;font-family:monospace;font-size:0.65rem;color:#5A6A8A;letter-spacing:0.1em;text-transform:uppercase">Mevcut</th>'
        f'<th style="padding:8px 14px;text-align:center;font-family:monospace;font-size:0.65rem;color:#1976D2;letter-spacing:0.1em;text-transform:uppercase">STP</th>'
        f'<th style="padding:8px 14px;text-align:center;font-family:monospace;font-size:0.65rem;color:#5A6A8A;letter-spacing:0.1em;text-transform:uppercase">Fark</th>'
        f'</tr></thead>'
        f'<tbody>{rows_html}</tbody>'
        f'</table>',
        unsafe_allow_html=True,
    )
 
 
 
def render_reprio_cards(display_df: pd.DataFrame, max_show: int = 60):
    shown = display_df.head(max_show)
 
    for _, row in shown.iterrows():
        cur = row["Current Priority"]
        stp = row["STP Priority"]
        changed = row["Changed"]
 
        cur_badge = priority_badge(cur) if cur else \
            '<span style="color:#3A4A6B;font-size:0.75rem">—</span>'
        stp_badge = priority_badge(stp)
 
        dtype = row.get("Desc Type", "")
        dtype_html = ""  # removed
 
        arrow_html = (f'<span class="arrow">→</span> {stp_badge}' if changed
                      else '<span style="color:#3A4A6B;font-size:0.75rem">unchanged</span>')
 
        extracted_parts = []
        if row.get("Extracted Actual"):
            extracted_parts.append(
                f'<span style="color:#E53935;font-size:0.68rem">● actual:</span> '
                f'<span style="color:#5A6A8A;font-size:0.72rem">{row["Extracted Actual"][:90]}</span>'
            )
        if row.get("Extracted Expected"):
            extracted_parts.append(
                f'<span style="color:#43A047;font-size:0.68rem">● expected:</span> '
                f'<span style="color:#5A6A8A;font-size:0.72rem">{row["Extracted Expected"][:90]}</span>'
            )
        extracted_html = ('<div style="margin:0.4rem 0">' + "<br>".join(extracted_parts) + '</div>'
                          if extracted_parts else "")
 
        st.markdown(f"""
        <div class="reprio-card">
            <div class="reprio-header">
                <span class="reprio-key">{row['Issue Key']}</span>
                {cur_badge}
                {arrow_html}
            </div>
            <div class="reprio-summary">{str(row['Summary'])[:120]}</div>
            {extracted_html}
            <div class="reprio-reason">💡 {row['Reason'][:180]}</div>
        </div>
        """, unsafe_allow_html=True)
 
    total = len(display_df)
    if total > max_show:
        st.markdown(
            f'<div style="text-align:center;color:#5A6A8A;font-size:0.75rem;'
            f'font-family:monospace;padding:0.5rem">'
            f'İlk {max_show} / {total} gösteriliyor — tam liste için CSV indir</div>',
            unsafe_allow_html=True,
        )
 
 
def tab_reprioritizer():
    # ── Upload bar ────────────────────────────────────────────
    col_up, col_info = st.columns([2, 1], gap="large")
    with col_up:
        st.markdown(
            '<div class="section-label" style="margin-top:0.4rem">CSV Yükle</div>',
            unsafe_allow_html=True,
        )
        uploaded = st.file_uploader(
            "CSV", type=["csv"], label_visibility="collapsed", key="reprio_upload_v3"
        )
    with col_info:
        st.markdown("""
        <div style="background:#FFFFFF;border:1px solid #D0D9E8;border-radius:8px;
                    padding:0.8rem 1rem;font-size:0.74rem;color:#5A6A8A;line-height:2;
                    margin-top:1.6rem">
            <b style="color:#1976D2;font-family:'JetBrains Mono',monospace;font-size:0.65rem;
                      letter-spacing:0.1em;text-transform:uppercase">Gerekli Kolonlar</b><br>
            <span style="color:#6B7A99">Issue key &nbsp;·&nbsp; Priority</span><br>
            <span style="color:#6B7A99">Summary &nbsp;·&nbsp; Description</span><br>
            <span style="font-size:0.68rem;color:#B0BED0;display:block;margin-top:4px">
            Description → Steps / Actual / Expected otomatik ayrıştırılır
            </span>
        </div>
        """, unsafe_allow_html=True)
 
    if not uploaded:
        st.markdown("""
        <div style="border:2px dashed #D0D9E8;border-radius:12px;padding:3rem;
                    text-align:center;color:#3A4A6B;font-family:'JetBrains Mono',monospace;
                    font-size:0.8rem;margin-top:1.2rem">
            <div style="font-size:2.5rem;margin-bottom:0.8rem">🔍</div>
            <div style="color:#5A6A8A">Keşif bulgularını içeren Jira CSV'yi yükle</div>
            <div style="font-size:0.68rem;margin-top:0.5rem;color:#B0BED0;line-height:1.8">
                Description alanından Steps · Actual · Expected otomatik çıkarılır<br>
                Crashlytics log dump'ları ayrı işaretlenir
            </div>
        </div>
        """, unsafe_allow_html=True)
        return
 
    # ── Run ───────────────────────────────────────────────────
    try:
        with st.spinner("Ayrıştırılıyor ve priority hesaplanıyor..."):
            df, fname = load_reprio_csv(uploaded)
            out_df    = run_reprioritizer(df)
    except ValueError as e:
        st.error(str(e))
        return
    except Exception as e:
        st.error(f"Hata: {e}")
        return
 
    # ── Summary stats ─────────────────────────────────────────
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    render_reprio_summary_stats(out_df)
    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
 
    # ── Filters ───────────────────────────────────────────────
    col_f1, col_f2, col_f3 = st.columns([1, 2, 1])
    with col_f1:
        show_changed = st.checkbox(
            "Sadece değişenleri göster", value=True, key="reprio_changed_v3"
        )
    with col_f2:
        filter_stp = st.multiselect(
            "STP Priority filtrele",
            ["Gating", "High", "Medium", "Low"],
            default=["Gating", "High", "Medium", "Low"],
            key="reprio_filter_v3",
            label_visibility="collapsed",
        )
    with col_f3:
        pass
 
    # ── Apply filters ─────────────────────────────────────────
    filtered = out_df[out_df["STP Priority"].isin(filter_stp)]
    if show_changed:
        filtered = filtered[filtered["Changed"]]
 
    st.markdown(
        f'<div class="section-label" style="margin-top:0.6rem">'
        f'{len(filtered)} issue · {int(out_df["Changed"].sum())} priority değişti</div>',
        unsafe_allow_html=True,
    )
 
    # ── Issue cards ───────────────────────────────────────────
    for _, row in filtered.head(80).iterrows():
        cur     = row["Current Priority"]
        stp     = row["STP Priority"]
        changed = row["Changed"]
        dtype   = row.get("Desc Type", "")
 
        cur_col = PRIORITY_COLORS.get(cur, "#78909C")
        stp_col = PRIORITY_COLORS.get(stp, "#78909C")
 
        # Header line
        cur_html = (f'<span class="p-badge" style="background:{cur_col}">{cur}</span>'
                    if cur else '<span style="color:#3A4A6B;font-size:0.75rem">—</span>')
        stp_html = f'<span class="p-badge" style="background:{stp_col}">{stp}</span>'
 
        if changed:
            change_html = f'{cur_html} <span class="arrow">→</span> {stp_html}'
        else:
            change_html = f'{stp_html} <span style="color:#B0BED0;font-size:0.72rem;font-family:monospace"> unchanged</span>'
 
 
 
        # Extracted content
        actual_html   = ""
        expected_html = ""
        steps_html    = ""
        if row.get("Extracted Actual"):
            actual_html = (
                f'<div style="margin-top:6px">'
                f'<span style="color:#E53935;font-family:\'JetBrains Mono\',monospace;'
                f'font-size:0.62rem;letter-spacing:0.08em;text-transform:uppercase">Actual</span>'
                f'<div style="color:#3A4A6B;font-size:0.78rem;margin-top:2px;'
                f'padding-left:0.5rem;border-left:2px solid #E5393533">'
                f'{row["Extracted Actual"][:150]}</div></div>'
            )
        if row.get("Extracted Expected"):
            expected_html = (
                f'<div style="margin-top:6px">'
                f'<span style="color:#43A047;font-family:\'JetBrains Mono\',monospace;'
                f'font-size:0.62rem;letter-spacing:0.08em;text-transform:uppercase">Expected</span>'
                f'<div style="color:#3A4A6B;font-size:0.78rem;margin-top:2px;'
                f'padding-left:0.5rem;border-left:2px solid #43A04733">'
                f'{row["Extracted Expected"][:150]}</div></div>'
            )
        if row.get("Extracted Steps"):
            steps_html = (
                f'<div style="margin-top:6px">'
                f'<span style="color:#1976D2;font-family:\'JetBrains Mono\',monospace;'
                f'font-size:0.62rem;letter-spacing:0.08em;text-transform:uppercase">Steps</span>'
                f'<div style="color:#3A4A6B;font-size:0.78rem;margin-top:2px;'
                f'padding-left:0.5rem;border-left:2px solid #4FC3F733">'
                f'{row["Extracted Steps"][:150]}</div></div>'
            )
 
        if dtype == "empty":
            content_block = (
                '<div style="margin-top:8px;font-size:0.75rem;color:#3A4A6B;'
                'font-style:italic">Description bilgisi yok — sadece summary ile degerlendirildi.</div>'
            )
        else:
            content_block = steps_html + actual_html + expected_html
 
        border_col = stp_col if changed else "#D0D9E8"
 
        with st.expander(
            f"{row['Issue Key']}  ·  {str(row['Summary'])[:80]}",
            expanded=False,
        ):
            reason_clean = str(row['Reason'])
            reason_clean = reason_clean.replace('[No strong signals. Defaulting to Medium — likely a functional scenario that needs manual review.]', '').strip()
            reason_clean = reason_clean.replace('[No strong signals. Defaulting to Low — likely a cosmetic or edge-case scenario.]', '').strip()
            reason_clean = reason_clean.strip(' ·').strip()
            st.markdown(
                f'<div style="padding:0.2rem 0 0.6rem 0">' +
                f'<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:0.8rem">' +
                f'<span style="font-family:JetBrains Mono,monospace;font-size:0.78rem;color:#1976D2;font-weight:700">{row["Issue Key"]}</span>' +
                f'</div>' +
                f'<div style="font-size:0.84rem;color:#1A2340;font-weight:500;margin-bottom:0.8rem">{str(row["Summary"])}</div>' +
                f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:0.6rem">' +
                f'<div style="background:#F4F6FA;border:1.5px solid #D0D9E8;border-radius:8px;padding:0.6rem 0.8rem">' +
                f'<div style="font-family:monospace;font-size:0.6rem;color:#7890B0;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:4px">Current Priority</div>' +
                f'<span class="p-badge" style="background:{cur_col}">{cur if cur else "—"}</span>' +
                f'</div>' +
                f'<div style="background:#EBF3FD;border:1.5px solid #90CAF9;border-radius:8px;padding:0.6rem 0.8rem">' +
                f'<div style="font-family:monospace;font-size:0.6rem;color:#1976D2;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:4px">STP Priority</div>' +
                f'<span class="p-badge" style="background:{stp_col}">{stp}</span>' +
                (f'&nbsp;<span style="font-size:0.7rem;color:#E53935;font-weight:600">▲ yükseldi</span>' if PRIORITY_ORDER.index(stp) < PRIORITY_ORDER.index(cur) and cur in PRIORITY_ORDER and stp in PRIORITY_ORDER else '') +
                (f'&nbsp;<span style="font-size:0.7rem;color:#43A047;font-weight:600">▼ düştü</span>' if PRIORITY_ORDER.index(stp) > PRIORITY_ORDER.index(cur) and cur in PRIORITY_ORDER and stp in PRIORITY_ORDER else '') +
                f'</div>' +
                f'</div>' +
                content_block +
                (f'<div style="margin-top:0.8rem;padding:0.6rem 0.8rem;background:#F0F4FA;border-radius:6px;border-left:3px solid #4FC3F7">' +
                 f'<div style="font-family:monospace;font-size:0.6rem;color:#1976D2;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:4px">Karar gerekcesi</div>' +
                 f'<div style="font-size:0.78rem;color:#5A6A8A;line-height:1.6">{reason_clean}</div>' +
                 f'</div>' if reason_clean else '') +
                f'</div>',
                unsafe_allow_html=True,
            )
 
    if len(filtered) > 80:
        st.markdown(
            f'<div style="text-align:center;color:#5A6A8A;font-size:0.75rem;'
            f'font-family:monospace;padding:0.5rem">'
            f'İlk 80 / {len(filtered)} gösteriliyor — tam liste için CSV indir</div>',
            unsafe_allow_html=True,
        )
 
    # ── Downloads ─────────────────────────────────────────────
    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    col_d1, col_d2 = st.columns(2)
    def _build_export(df):
        out = df[["Issue Key", "Summary", "Current Priority", "STP Priority", "Reason"]].copy()
        out.columns = ["Issue Key", "Summary", "Current Priority", "STP Priority", "STP Reason"]
        return out
 
    with col_d1:
        diff_export = _build_export(out_df[out_df["Changed"]])
        st.download_button(
            "⬇ Değişen issue'lar (CSV)",
            data=diff_export.to_csv(index=False).encode("utf-8"),
            file_name=f"REPRIO_DIFF_{Path(fname).stem}.csv",
            mime="text/csv", key="reprio_dl_diff_v3",
        )
    with col_d2:
        all_export = _build_export(out_df)
        st.download_button(
            "⬇ Tüm analiz (CSV)",
            data=all_export.to_csv(index=False).encode("utf-8"),
            file_name=f"REPRIO_ALL_{Path(fname).stem}.csv",
            mime="text/csv", key="reprio_dl_all_v3",
        )
 
 
# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════
 
def main():
    st.set_page_config(
        page_title="STP Analyzer — BiP QA",
        layout="wide",
        page_icon="🎯",
        initial_sidebar_state="collapsed",
    )
    inject_css()
 
    st.markdown("""
    <div class="stp-header">
        <div class="stp-title"><span>STP</span> Analyzer</div>
        <div class="stp-subtitle">
            BiP QA &nbsp;·&nbsp;
            Defined Scenario PreReview &nbsp;·&nbsp;
            Exploratory RePrioritizer
        </div>
    </div>
    <div class="stp-divider"></div>
    """, unsafe_allow_html=True)
 
    tab1, tab2 = st.tabs([
        "🎯  Defined Scenario PreReview",
        "🔍  Exploratory RePrioritizer",
    ])
 
    with tab1:
        tab_prereview()
 
    with tab2:
        tab_reprioritizer()
 
 
if __name__ == "__main__":
    main()
 
