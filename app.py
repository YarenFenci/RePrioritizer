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
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Syne:wght@400;600;700;800&family=DM+Sans:wght@300;400;500&display=swap');

    html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
    .stApp { background: #0A0E1A; }
    .block-container { padding-top: 1rem !important; max-width: 1300px !important; }

    .stp-header { padding: 1.8rem 0 1rem 0; }
    .stp-title {
        font-family: 'Syne', sans-serif; font-size: 2rem; font-weight: 800;
        color: #F0F4FF; letter-spacing: -0.03em; line-height: 1.1; margin: 0;
    }
    .stp-title span { color: #4FC3F7; }
    .stp-subtitle { font-size: 0.82rem; color: #6B7A99; margin-top: 0.4rem; }
    .stp-divider {
        height: 1px;
        background: linear-gradient(90deg, #4FC3F7 0%, #1E2761 60%, transparent 100%);
        margin: 0.8rem 0 0.5rem 0;
    }

    .form-label {
        font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; font-weight: 600;
        color: #4FC3F7; letter-spacing: 0.12em; text-transform: uppercase; margin-bottom: 0.4rem;
    }
    .section-label {
        font-family: 'JetBrains Mono', monospace; font-size: 0.65rem; font-weight: 600;
        color: #3A6080; letter-spacing: 0.1em; text-transform: uppercase;
        margin: 0.8rem 0 0.3rem 0;
    }

    .stTextInput input, .stTextArea textarea {
        background: #0D1321 !important; border: 1px solid #1E2761 !important;
        border-radius: 8px !important; color: #E8EEFF !important;
        font-family: 'DM Sans', sans-serif !important; font-size: 0.88rem !important;
    }
    .stTextInput input:focus, .stTextArea textarea:focus {
        border-color: #4FC3F7 !important;
        box-shadow: 0 0 0 2px rgba(79,195,247,0.12) !important;
    }
    .stSelectbox > div > div {
        background: #0D1321 !important; border: 1px solid #1E2761 !important;
        border-radius: 8px !important; color: #E8EEFF !important;
    }
    .stButton > button {
        background: linear-gradient(135deg, #1565C0, #0D47A1) !important;
        color: #E8F5FF !important; border: none !important; border-radius: 8px !important;
        font-family: 'Syne', sans-serif !important; font-weight: 700 !important;
        font-size: 0.9rem !important; width: 100% !important;
    }
    .stButton > button:hover {
        background: linear-gradient(135deg, #1976D2, #1565C0) !important;
        transform: translateY(-1px) !important;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 4px; background: #0D1321 !important;
        border-bottom: 1px solid #1E2761 !important;
    }
    .stTabs [data-baseweb="tab"] {
        font-family: 'JetBrains Mono', monospace !important; font-size: 0.72rem !important;
        color: #4A5A7A !important; padding: 0.5rem 1.2rem !important;
        border-radius: 6px 6px 0 0 !important;
    }
    .stTabs [aria-selected="true"] {
        color: #4FC3F7 !important; background: #111827 !important;
        border-bottom: 2px solid #4FC3F7 !important;
    }

    .result-card { border-radius: 12px; padding: 1.4rem; margin-bottom: 1rem; border: 1px solid; }
    .result-priority-label {
        font-family: 'JetBrains Mono', monospace; font-size: 0.65rem; font-weight: 600;
        letter-spacing: 0.15em; text-transform: uppercase; margin-bottom: 0.3rem;
    }
    .result-priority-value {
        font-family: 'Syne', sans-serif; font-size: 2rem; font-weight: 800;
        letter-spacing: -0.02em; line-height: 1; margin-bottom: 0.4rem;
    }
    .result-desc { font-size: 0.82rem; opacity: 0.75; line-height: 1.4; }

    .reason-box {
        background: #0D1321; border: 1px solid #1E2761; border-left: 3px solid #4FC3F7;
        border-radius: 8px; padding: 1rem 1.2rem; margin-top: 0.8rem;
    }
    .reason-title {
        font-family: 'JetBrains Mono', monospace; font-size: 0.65rem; color: #4FC3F7;
        letter-spacing: 0.12em; text-transform: uppercase; margin-bottom: 0.4rem;
    }
    .reason-text { font-size: 0.83rem; color: #C8D4F0; line-height: 1.6; }

    .adjust-box {
        background: #0D1B2A; border: 1px solid #1E3A5F; border-radius: 8px;
        padding: 0.8rem 1rem; margin-top: 0.8rem; font-size: 0.82rem; line-height: 1.6;
    }
    .adjust-box-label {
        font-family: 'JetBrains Mono', monospace; font-size: 0.6rem; letter-spacing: 0.12em;
        text-transform: uppercase; margin-bottom: 0.3rem; font-weight: 600; color: #4FC3F7;
    }

    .keyword-box {
        background: #0D1321; border: 1px solid #1E2761; border-radius: 8px;
        padding: 0.8rem 1.1rem; margin-top: 0.8rem;
    }
    .kw-chip {
        display: inline-block; background: #1A2340; border: 1px solid #2A3560;
        border-radius: 4px; padding: 2px 8px; font-family: 'JetBrains Mono', monospace;
        font-size: 0.68rem; color: #8BA7D9; margin: 2px 3px;
    }

    .cmp-box {
        background: #0D1321; border: 1px solid #1E2761; border-radius: 8px;
        padding: 0.8rem 1rem; margin-top: 0.5rem;
    }
    .cmp-label {
        font-family: 'JetBrains Mono', monospace; font-size: 0.6rem; letter-spacing: 0.1em;
        text-transform: uppercase; margin-bottom: 0.3rem;
    }
    .cmp-text { font-size: 0.82rem; color: #C8D4F0; line-height: 1.5; }

    .stat-box {
        background: #0D1321; border: 1px solid #1E2761; border-radius: 8px;
        padding: 0.8rem 1rem; text-align: center;
    }
    .stat-num {
        font-family: 'JetBrains Mono', monospace; font-size: 1.4rem; font-weight: 700; color: #4FC3F7;
    }
    .stat-label { font-size: 0.7rem; color: #4A5A7A; margin-top: 2px; }

    .p-badge {
        display: inline-block; padding: 2px 9px; border-radius: 4px;
        font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; font-weight: 700; color: #fff;
    }

    .hist-row {
        display: flex; align-items: center; gap: 10px; padding: 0.6rem 0.8rem;
        border-radius: 6px; background: #111827; border: 1px solid #1A2340;
        margin-bottom: 6px; font-size: 0.82rem;
    }
    .hist-key { font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; color: #4FC3F7; min-width: 36px; }
    .hist-summary { flex: 1; color: #A0B0CC; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .hist-badge {
        font-family: 'JetBrains Mono', monospace; font-size: 0.68rem; font-weight: 700;
        padding: 2px 9px; border-radius: 4px; color: #fff; white-space: nowrap;
    }

    .reprio-card {
        background: #0D1321; border: 1px solid #1E2761; border-radius: 8px;
        padding: 0.8rem 1rem; margin-bottom: 0.5rem;
    }
    .reprio-header { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 0.4rem; }
    .reprio-key { font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; color: #4FC3F7; font-weight: 600; }
    .reprio-summary { font-size: 0.82rem; color: #A0B0CC; margin-bottom: 0.3rem; }
    .reprio-reason { font-size: 0.72rem; color: #4A6A8A; font-style: italic; padding-left: 0.5rem; border-left: 2px solid #1E2761; }
    .arrow { color: #4FC3F7; }
    .desc-type-badge {
        font-family: 'JetBrains Mono', monospace; font-size: 0.62rem; padding: 1px 7px;
        border-radius: 10px; font-weight: 600;
    }

    div[data-testid="stFileUploader"] {
        border: 1px solid #1E2761 !important; border-radius: 8px !important; background: #0D1321 !important;
    }
    div[data-testid="stDataFrame"] { border: 1px solid #1E2761; border-radius: 8px; }
    section[data-testid="stSidebar"] { background: #0D1321 !important; border-right: 1px solid #1E2761 !important; }
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
            key="pre_summary",
        )

        st.markdown('<div class="section-label">Steps to Reproduce</div>', unsafe_allow_html=True)
        steps = st.text_area(
            "Steps",
            placeholder="1. Open chat\n2. Tap voice message\n3. Record and send\n4. App force closes",
            height=100, label_visibility="collapsed", key="pre_steps",
        )

        col_a, col_e = st.columns(2)
        with col_a:
            st.markdown('<div class="section-label">🔴 Actual Result</div>', unsafe_allow_html=True)
            actual = st.text_area(
                "Actual", placeholder="What happens?",
                height=90, label_visibility="collapsed", key="pre_actual",
            )
        with col_e:
            st.markdown('<div class="section-label">🟢 Expected Result</div>', unsafe_allow_html=True)
            expected = st.text_area(
                "Expected", placeholder="What should happen?",
                height=90, label_visibility="collapsed", key="pre_expected",
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
                               label_visibility="collapsed", key="pre_freq")
            freq = freq_keys[freq_display.index(sel)]

        with col_d:
            st.markdown('<div class="section-label">📱 Device / OS Scope</div>', unsafe_allow_html=True)
            live = (st.session_state.get("pre_summary", "") + " " +
                    st.session_state.get("pre_steps", ""))
            auto_dev = auto_detect_device(live)
            device_scope = st.text_input(
                "Device", value=auto_dev,
                placeholder="e.g. Samsung A5, iOS 16…",
                label_visibility="collapsed", key="pre_device",
            )
            if auto_dev and auto_dev.lower() == device_scope.strip().lower():
                st.markdown('<div style="font-size:0.7rem;color:#FF9800;margin-top:3px">⚡ Auto-detected</div>', unsafe_allow_html=True)
            elif device_scope.strip():
                st.markdown('<div style="font-size:0.7rem;color:#43A047;margin-top:3px">✏️ Manually set</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div style="font-size:0.7rem;color:#3A4A6B;margin-top:3px">Leave empty = all devices</div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        analyze = st.button("▶  Analyze Priority", key="pre_analyze")

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
        <div style="background:#0D1321;border:1px solid #1E2761;border-left:3px solid #E53935;
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
            <div style="height:220px;border:1px dashed #1E2761;border-radius:12px;
                display:flex;flex-direction:column;align-items:center;justify-content:center;
                color:#2A3A5C;font-family:'JetBrains Mono',monospace;font-size:0.8rem;
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
            key=f"dl_pre_{len(st.session_state.history)}",
        )


# ═══════════════════════════════════════════════════════════════
# Tab 2 — Exploratory RePrioritizer
# ═══════════════════════════════════════════════════════════════

def render_reprio_summary_stats(out_df: pd.DataFrame):
    n_total    = len(out_df)
    n_changed  = int(out_df["Changed"].sum())
    n_crashlog = int((out_df["Desc Type"] == "crashlytics_log").sum())

    c1, c2, c3, c4, c5 = st.columns(5)
    for col, num, label, color in [
        (c1, n_total,   "Total Issues",    "#4FC3F7"),
        (c2, n_changed, "Priority Changed", "#FB8C00"),
        (c3, int(out_df["STP Priority"].eq("Gating").sum()), "Gating (STP)", "#E53935"),
        (c4, int(out_df["STP Priority"].eq("High").sum()),   "High (STP)",   "#FB8C00"),
        (c5, n_crashlog, "Crashlytics Logs", "#78909C"),
    ]:
        col.markdown(
            f'<div class="stat-box"><div class="stat-num" style="color:{color}">{num}</div>'
            f'<div class="stat-label">{label}</div></div>',
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
        if dtype == "crashlytics_log":
            dtype_html = ('<span class="desc-type-badge" style="background:#1A1A2E;'
                          'color:#78909C;border:1px solid #2A2A4E">📊 Crashlytics Log</span>')
        elif dtype == "bug_report":
            dtype_html = ('<span class="desc-type-badge" style="background:#0D2A1A;'
                          'color:#43A047;border:1px solid #1A4A2A">🐛 Bug Report</span>')
        else:
            dtype_html = ('<span class="desc-type-badge" style="background:#1A1A2E;'
                          'color:#4A5A7A;border:1px solid #2A2A4E">📄 No Desc</span>')

        arrow_html = (f'<span class="arrow">→</span> {stp_badge}' if changed
                      else '<span style="color:#3A4A6B;font-size:0.75rem">unchanged</span>')

        extracted_parts = []
        if row.get("Extracted Actual"):
            extracted_parts.append(
                f'<span style="color:#E53935;font-size:0.68rem">● actual:</span> '
                f'<span style="color:#8A9ABB;font-size:0.72rem">{row["Extracted Actual"][:90]}</span>'
            )
        if row.get("Extracted Expected"):
            extracted_parts.append(
                f'<span style="color:#43A047;font-size:0.68rem">● expected:</span> '
                f'<span style="color:#8A9ABB;font-size:0.72rem">{row["Extracted Expected"][:90]}</span>'
            )
        extracted_html = ('<div style="margin:0.4rem 0">' + "<br>".join(extracted_parts) + '</div>'
                          if extracted_parts else "")

        st.markdown(f"""
        <div class="reprio-card">
            <div class="reprio-header">
                <span class="reprio-key">{row['Issue Key']}</span>
                {cur_badge}
                {arrow_html}
                {dtype_html}
            </div>
            <div class="reprio-summary">{str(row['Summary'])[:120]}</div>
            {extracted_html}
            <div class="reprio-reason">💡 {row['Reason'][:180]}</div>
        </div>
        """, unsafe_allow_html=True)

    total = len(display_df)
    if total > max_show:
        st.markdown(
            f'<div style="text-align:center;color:#4A5A7A;font-size:0.75rem;'
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
            "CSV", type=["csv"], label_visibility="collapsed", key="reprio_upload"
        )
    with col_info:
        st.markdown("""
        <div style="background:#0D1321;border:1px solid #1E2761;border-radius:8px;
                    padding:0.8rem 1rem;font-size:0.74rem;color:#4A5A7A;line-height:2;
                    margin-top:1.6rem">
            <b style="color:#4FC3F7;font-family:'JetBrains Mono',monospace;font-size:0.65rem;
                      letter-spacing:0.1em;text-transform:uppercase">Gerekli Kolonlar</b><br>
            <span style="color:#6B7A99">Issue key &nbsp;·&nbsp; Priority</span><br>
            <span style="color:#6B7A99">Summary &nbsp;·&nbsp; Description</span><br>
            <span style="font-size:0.68rem;color:#2A3A5C;display:block;margin-top:4px">
            Description → Steps / Actual / Expected otomatik ayrıştırılır
            </span>
        </div>
        """, unsafe_allow_html=True)

    if not uploaded:
        st.markdown("""
        <div style="border:2px dashed #1E2761;border-radius:12px;padding:3rem;
                    text-align:center;color:#3A4A6B;font-family:'JetBrains Mono',monospace;
                    font-size:0.8rem;margin-top:1.2rem">
            <div style="font-size:2.5rem;margin-bottom:0.8rem">🔍</div>
            <div style="color:#4A5A7A">Keşif bulgularını içeren Jira CSV'yi yükle</div>
            <div style="font-size:0.68rem;margin-top:0.5rem;color:#2A3A5C;line-height:1.8">
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
            "Sadece değişenleri göster", value=True, key="reprio_changed"
        )
    with col_f2:
        filter_stp = st.multiselect(
            "STP Priority filtrele",
            ["Gating", "High", "Medium", "Low"],
            default=["Gating", "High", "Medium", "Low"],
            key="reprio_filter",
            label_visibility="collapsed",
        )
    with col_f3:
        filter_dtype = st.multiselect(
            "Desc tipi",
            ["bug_report", "crashlytics_log", "empty"],
            default=["bug_report", "crashlytics_log", "empty"],
            key="reprio_dtype",
            label_visibility="collapsed",
        )

    # ── Apply filters ─────────────────────────────────────────
    filtered = out_df[
        out_df["STP Priority"].isin(filter_stp) &
        out_df["Desc Type"].isin(filter_dtype)
    ]
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
            change_html = f'{stp_html} <span style="color:#2A3A5C;font-size:0.72rem;font-family:monospace"> unchanged</span>'

        if dtype == "crashlytics_log":
            dtype_html = ('<span class="desc-type-badge" style="background:#1A1A2E;'
                          'color:#78909C;border:1px solid #2A2A4E">📊 Crashlytics</span>')
        elif dtype == "bug_report":
            dtype_html = ('<span class="desc-type-badge" style="background:#0D2A1A;'
                          'color:#43A047;border:1px solid #1A4A2A">🐛 Bug Report</span>')
        else:
            dtype_html = ('<span class="desc-type-badge" style="background:#1A1A2E;'
                          'color:#4A5A7A;border:1px solid #2A2A4E">📄 No Desc</span>')

        # Extracted content
        actual_html   = ""
        expected_html = ""
        steps_html    = ""
        if row.get("Extracted Actual"):
            actual_html = (
                f'<div style="margin-top:6px">'
                f'<span style="color:#E53935;font-family:\'JetBrains Mono\',monospace;'
                f'font-size:0.62rem;letter-spacing:0.08em;text-transform:uppercase">Actual</span>'
                f'<div style="color:#C8D4F0;font-size:0.78rem;margin-top:2px;'
                f'padding-left:0.5rem;border-left:2px solid #E5393533">'
                f'{row["Extracted Actual"][:150]}</div></div>'
            )
        if row.get("Extracted Expected"):
            expected_html = (
                f'<div style="margin-top:6px">'
                f'<span style="color:#43A047;font-family:\'JetBrains Mono\',monospace;'
                f'font-size:0.62rem;letter-spacing:0.08em;text-transform:uppercase">Expected</span>'
                f'<div style="color:#C8D4F0;font-size:0.78rem;margin-top:2px;'
                f'padding-left:0.5rem;border-left:2px solid #43A04733">'
                f'{row["Extracted Expected"][:150]}</div></div>'
            )
        if row.get("Extracted Steps"):
            steps_html = (
                f'<div style="margin-top:6px">'
                f'<span style="color:#4FC3F7;font-family:\'JetBrains Mono\',monospace;'
                f'font-size:0.62rem;letter-spacing:0.08em;text-transform:uppercase">Steps</span>'
                f'<div style="color:#C8D4F0;font-size:0.78rem;margin-top:2px;'
                f'padding-left:0.5rem;border-left:2px solid #4FC3F733">'
                f'{row["Extracted Steps"][:150]}</div></div>'
            )

        content_block = steps_html + actual_html + expected_html

        border_col = stp_col if changed else "#1E2761"

        with st.expander(
            f"{row['Issue Key']}  ·  {str(row['Summary'])[:80]}",
            expanded=False,
        ):
            st.markdown(f"""
            <div style="padding:0.2rem 0 0.6rem 0">
                <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:0.8rem">
                    <span style="font-family:'JetBrains Mono',monospace;font-size:0.78rem;
                                 color:#4FC3F7;font-weight:600">{row['Issue Key']}</span>
                    {change_html}
                    {dtype_html}
                </div>
                <div style="font-size:0.82rem;color:#A0B0CC;margin-bottom:0.6rem">
                    {str(row['Summary'])}
                </div>
                {content_block}
                <div style="margin-top:0.8rem;padding:0.6rem 0.8rem;
                            background:#0A1020;border-radius:6px;
                            border-left:3px solid #4FC3F7">
                    <span style="font-family:'JetBrains Mono',monospace;font-size:0.6rem;
                                 color:#4FC3F7;letter-spacing:0.1em;
                                 text-transform:uppercase">Karar gerekçesi</span>
                    <div style="font-size:0.78rem;color:#8A9ABB;margin-top:4px;line-height:1.6">
                        {row['Reason'][:300]}
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

    if len(filtered) > 80:
        st.markdown(
            f'<div style="text-align:center;color:#4A5A7A;font-size:0.75rem;'
            f'font-family:monospace;padding:0.5rem">'
            f'İlk 80 / {len(filtered)} gösteriliyor — tam liste için CSV indir</div>',
            unsafe_allow_html=True,
        )

    # ── Downloads ─────────────────────────────────────────────
    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        diff = out_df[out_df["Changed"]]
        st.download_button(
            "⬇ Değişen issue'lar (CSV)",
            data=diff.to_csv(index=False).encode("utf-8"),
            file_name=f"REPRIO_DIFF_{Path(fname).stem}.csv",
            mime="text/csv", key="reprio_dl_diff",
        )
    with col_d2:
        st.download_button(
            "⬇ Tüm analiz (CSV)",
            data=out_df.to_csv(index=False).encode("utf-8"),
            file_name=f"REPRIO_ALL_{Path(fname).stem}.csv",
            mime="text/csv", key="reprio_dl_all",
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
        <div class="stp-title">STP <span>Analyzer</span></div>
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
