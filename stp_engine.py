"""
STP Engine — BiP QA priority assignment (revised)

Amaç:
- Görsel / layout / spacing bug'ları gereksiz yere High/Gating'e çıkarmamak
- Core feature mention ile core failure'ı ayırmak
- Crash / freeze / gerçek broken flow durumlarını yine güçlü şekilde yakalamak

Öncelik mantığı:
Gating  = crash / freeze / stuck / core flow tamamen broken
High    = functional bug — feature çalışıyor ama yanlış sonuç / core action fail değilse önemli functional issue
Medium  = UX / secondary behaviour — visual glitch, layout, rotation, ordering, proximity, non-blocking UI issue
Low     = saf cosmetic — typo, color, icon, minor font/text issue
Default = Medium
"""

import re
from typing import Tuple

PRIORITY_ORDER = ["Gating", "High", "Medium", "Low"]

REASON_MAP = {
    "Gating": "App crash / freeze / core flow broken — blocks release. Must fix before shipping.",
    "High":   "Functional bug — important feature behaves incorrectly. Fix within 2 weeks.",
    "Medium": "UX / secondary behaviour — non-blocking. Fix within 6 weeks.",
    "Low":    "Cosmetic / edge case — no functional impact.",
}

FREQ_OPTIONS = ["always", "frequently", "occasionally", "rarely", "once"]
FREQ_DROPS   = {"always": 0, "frequently": 0, "occasionally": 1, "rarely": 1, "once": 2}
FREQ_LABELS  = {
    "always":       "Always reproducible",
    "frequently":   "Frequently reproducible",
    "occasionally": "Occasionally reproducible",
    "rarely":       "Rarely reproducible",
    "once":         "Reproduced once",
}

# ═══════════════════════════════════════════════════════════════
# Base rule sets
# ═══════════════════════════════════════════════════════════════

# Hard crash / freeze
HARD_CRASH_TERMS = [
    "crash", "crashes", "crashed", "force close",
    "fatal error", "anr", "not responding",
    "çöküyor", "çöktü", "kapanıyor", "uygulama kapandı",
]

FREEZE_TERMS = [
    "freeze", "frozen", "hang", "hangs", "hung",
    "stuck", "unresponsive",
    "donuyor", "dondu", "takılıyor", "takıldı",
    "askıda", "yanıt vermiyor",
]

# Real core failures → strong Gating
CORE_FAILURE_TERMS = [
    # Open / launch
    "cannot open", "can't open", "cant open", "won't open",
    "unable to open", "fails to open", "app not opening",
    "açılmıyor", "açılamıyor", "girilemiyor",

    # Chat / message hard fail
    "cannot send", "can't send", "message not sent", "failed to send",
    "unable to send", "send failed",
    "gönderilemiyor", "gönderilemedi",
    "cannot receive", "can't receive", "message not received",
    "messages not delivered", "alınamıyor",

    # Auth
    "cannot login", "can't login", "login fail", "login failed",
    "giriş yapılamıyor", "login olmuyor",

    # Calls
    "cannot call", "can't call", "cannot start call", "call not started",
    "cannot receive call", "cannot make call",

    # Chat open fail
    "cannot open chat", "chat not open", "cannot load chat", "chat not load",

    # Status / channels
    "cannot view status", "status not open",
    "cannot share status", "cannot upload status",
    "cannot open channel", "channel not open",

    # App / load
    "cannot load", "not load", "app not open",
]

# Existing Gating pool for compatibility
GATING_TERMS = HARD_CRASH_TERMS + FREEZE_TERMS + CORE_FAILURE_TERMS

# High = important functional validation / important functional wrong behavior
HIGH_TERMS = [
    # Functional wrong behaviour
    "not working", "does not work", "doesn't work",
    "not loading", "not updating",
    "wrong data", "wrong result", "incorrect",
    "missing", "error occurs", "shows error",

    # Chat
    "send message", "message sent",
    "receive message", "message received",
    "message delivered", "message seen",
    "delete message", "edit message", "reply message", "forward message",

    # Calls
    "voice call", "video call", "call started",
    "incoming call", "outgoing call",
    "call connected", "call established", "call answered", "call ended",

    # Channels
    "channel post", "post sent", "share",
    "subscribe", "unsubscribe", "join channel",

    # Status
    "share status", "status shared", "status uploaded",
    "view status", "status displayed", "status seen",
    "delete status", "status deleted",

    # Emoji / sticker / reaction
    "send emoji", "emoji sent",
    "send sticker", "sticker sent",
    "reaction", "react", "postback",

    # More / settings / profile
    "settings saved", "settings changed",
    "profile updated", "logout success", "login success",
    "notification received", "notification sent",
    "change password", "privacy change", "privacy updated",
]

# Medium = UX / secondary / navigation / presentation
MEDIUM_TERMS = [
    "search", "filter", "list", "display", "shown", "scroll",
    "tab", "icon", "category", "panel", "picker", "keyboard",
    "menu", "navigate", "view", "preview", "thumbnail",
    "history", "log", "timer", "duration",
    "chat list", "open conversation", "status list", "call history",
    "open settings", "select",
]

# Visual/layout → mostly Medium unless pure cosmetic
VISUAL_LAYOUT_TERMS = [
    "gap", "extra gap", "huge gap", "big gap",
    "spacing", "too close", "very close",
    "alignment", "misaligned", "overlap", "overlapped",
    "layout", "position", "wrong position",
    "padding", "margin",
    "landscape", "portrait", "rotate", "rotating", "rotation",
    "ui", "visual", "display issue",
    "truncated", "cut off", "cropped",
    "before first message",
]

# Pure cosmetic → Low
LOW_COSMETIC_TERMS = [
    "typo", "spelling", "misspelling",
    "wrong color", "color issue", "font issue", "wrong font",
    "wrong icon", "minor ui", "cosmetic",
]

# Core feature nouns/context — these DO NOT escalate by themselves
CORE_FEATURE_TERMS = [
    "message", "chat", "call", "status", "story", "channel",
    "emoji", "sticker", "notification", "profile", "settings",
]

SECONDARY_FEATURE_TERMS = [
    "theme", "wallpaper", "font", "color", "icon", "animation",
    "padding", "margin", "layout", "alignment", "spacing",
]

# ═══════════════════════════════════════════════════════════════
# Feature extensions
# ═══════════════════════════════════════════════════════════════
def _feature_extensions(fn: str):
    fn = (fn or "").lower()
    g, h, m = [], [], []

    if "call" in fn:
        g += ["cannot receive call", "cannot make call"]
        h += ["call connected", "call established", "call answered", "call ended"]
        m += ["call history", "duration", "timer", "log"]

    elif "chat" in fn:
        g += [
            "cannot open chat", "chat not open",
            "cannot send message", "cannot receive message",
            "chat not load", "cannot load chat"
        ]
        h += [
            "message delivered", "message seen", "delete message",
            "edit message", "reply message", "forward message"
        ]
        m += ["chat list", "open conversation"]

    elif "channel" in fn:
        g += ["cannot open channel", "channel not open"]
        h += ["channel post", "post sent", "subscribe", "unsubscribe", "join channel"]
        m += ["channel list"]

    elif "status" in fn or "story" in fn:
        g += [
            "cannot view status", "status not open",
            "cannot share status", "cannot upload status"
        ]
        h += [
            "share status", "status shared", "status uploaded",
            "view status", "status displayed", "status seen",
            "delete status", "status deleted"
        ]
        m += ["status list", "thumbnail", "preview"]

    elif "more" in fn or "other" in fn:
        g += ["cannot logout", "cannot load", "not load", "app not open"]
        h += [
            "settings saved", "settings changed", "profile updated",
            "logout success", "login success", "notification received",
            "notification sent", "change password", "privacy change", "privacy updated"
        ]
        m += ["open settings", "select", "menu", "navigate", "view"]

    elif "emoji" in fn or "sticker" in fn:
        g += ["emoji not sent", "cannot react"]
        h += ["react", "postback"]
        m += ["recent", "favorites", "favourite", "skin tone", "picker", "panel"]

    return g, h, m


# ═══════════════════════════════════════════════════════════════
# Matching helpers
# ═══════════════════════════════════════════════════════════════
def _match(text: str, term: str) -> bool:
    if not term:
        return False
    if " " in term:
        return term in text
    if len(term) <= 6:
        return bool(re.search(
            r"(?<![a-zA-Z\u00c0-\u024f])" + re.escape(term) + r"(?![a-zA-Z\u00c0-\u024f])",
            text
        ))
    return term in text

def _hit(text: str, terms: list):
    for t in terms:
        if _match(text, t):
            return t
    return ""

def _has_any(text: str, terms: list) -> bool:
    return bool(_hit(text, terms))


# ═══════════════════════════════════════════════════════════════
# Context helpers
# ═══════════════════════════════════════════════════════════════
def _is_crashlytics_log(summary: str) -> bool:
    s = (summary or "").lower().strip()
    return bool(re.match(r"^crashlytics\s*[-|]", s))

def _has_core_feature(text: str) -> bool:
    t = (text or "").lower()
    return any(_match(t, kw) for kw in CORE_FEATURE_TERMS)

def _is_secondary_feature(text: str) -> bool:
    t = (text or "").lower()
    return any(_match(t, kw) for kw in SECONDARY_FEATURE_TERMS)


# ═══════════════════════════════════════════════════════════════
# Decision engine
# ═══════════════════════════════════════════════════════════════
def _decide(summary: str, steps: str, expected: str,
            feature_name: str = "") -> Tuple[str, str]:
    """
    Returns (priority, hit_term)

    Decision order:
    1) Crashlytics log → KEEP
    2) Pure cosmetic → Low
    3) Visual/layout/orientation + no real core failure → Medium
    4) Crash/freeze/core broken → Gating
    5) Functional issue / important validation → High
    6) UX/navigation → Medium
    7) Default → Medium
    """

    if _is_crashlytics_log(summary):
        return "KEEP", "crashlytics_log"

    eg, eh, em = _feature_extensions(feature_name)

    s  = (summary or "").lower()
    st = (steps or "").lower()
    ex = (expected or "").lower()
    se = (st + " " + ex).strip()
    full = (s + " " + se).strip()

    all_g = GATING_TERMS + eg
    all_h = HIGH_TERMS + eh
    all_m = MEDIUM_TERMS + em

    # Hits
    cosmetic_hit = _hit(full, LOW_COSMETIC_TERMS)
    visual_hit   = _hit(full, VISUAL_LAYOUT_TERMS)
    gating_hit   = _hit(full, all_g)
    high_hit     = _hit(full, all_h)
    medium_hit   = _hit(full, all_m)
    crash_hit    = _hit(full, HARD_CRASH_TERMS + FREEZE_TERMS)

    # 1) Pure cosmetic → Low
    if cosmetic_hit and not gating_hit and not high_hit:
        return "Low", cosmetic_hit

    # 2) Visual/layout override
    # If issue is clearly visual/layout/orientation and there is no real core failure,
    # do NOT escalate just because chat/message/call terms appear.
    if visual_hit and not gating_hit and not crash_hit:
        return "Medium", f"visual-layout: {visual_hit}"

    # 3) Crash / freeze
    if crash_hit:
        if _is_secondary_feature(full) and not _has_core_feature(full):
            return "High", f"secondary-feature crash: {crash_hit}"
        return "Gating", crash_hit

    # 4) Real gating
    if gating_hit:
        return "Gating", gating_hit

    # 5) Functional High
    if high_hit:
        return "High", high_hit

    # 6) Medium UX/navigation
    if medium_hit:
        return "Medium", medium_hit

    # 7) Default
    return "Medium", ""


# ═══════════════════════════════════════════════════════════════
# Device / OS scope
# ═══════════════════════════════════════════════════════════════
DEVICE_PATTERNS  = [
    r"\bredmi\s*\d+\b", r"\bxiaomi\b", r"\bsamsung\s+[a-z]\d+", r"\bhuawei\b",
    r"\biphone\s*\d+", r"\bpixel\s*\d+",
    r"\brealme\b", r"\bvivo\b", r"\bnokia\b", r"\bpoco\b",
    r"\bmoto\b", r"\bmotorola\b", r"\bgalaxy\s+[a-z]\d+",
]
OS_PATTERNS = [
    r"\bandroid\s*\d+", r"\bios\s*\d+", r"\bmiui\s*\d+",
    r"\bone\s*ui\s*\d+", r"\bharmonyos\b", r"\bcoloros\b",
]
CHIPSET_PATTERNS = [
    r"\bsnapdragon\s*\d+", r"\bexynos\s*\d+", r"\bdimensity\s*\d+",
    r"\bkirin\s*\d+", r"\ba\d+\s*chip\b", r"\bbionic\b",
    r"\bmediatek\b", r"\bhelio\b",
]

def detect_device_os_scope(text: str) -> Tuple[bool, str, str]:
    t = (text or "").lower()
    for pat in CHIPSET_PATTERNS:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            return True, "chipset", m.group(0)

    for pat in OS_PATTERNS:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            return True, "os_version", m.group(0)

    matches = []
    for pat in DEVICE_PATTERNS:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            matches.append(m.group(0))

    if len(matches) == 1:
        return True, "single_device_repro", matches[0]
    if len(matches) > 1:
        return True, "device", ", ".join(matches[:2])

    return False, "", ""


# ═══════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════
def decide_priority(
    text: str = "",
    actual_result: str = "",
    expected_result: str = "",
    summary: str = "",
    steps: str = "",
    reproduce_frequency: str = "always",
    device_scope: str = "",
    feature_name: str = "",
    current_priority: str = "",
) -> Tuple[str, bool, str, str, str, str]:
    """
    Returns:
    (priority, is_scoped, scope_type, scope_detail, reason, adjusted_note)
    """
    _sum  = (summary or text or "").strip()
    _st   = (steps or actual_result or "").strip()
    _ex   = (expected_result or "").strip()
    combo = (_sum + " " + _st + " " + _ex).lower()

    # Scope
    auto_sc, auto_st, auto_sd = detect_device_os_scope(combo)
    if device_scope.strip():
        is_scoped, scope_type, scope_detail = True, "manual", device_scope.strip()
    else:
        is_scoped, scope_type, scope_detail = auto_sc, auto_st, auto_sd

    # Frequency
    freq = (reproduce_frequency or "always").lower().strip()
    if freq not in FREQ_OPTIONS:
        freq = "always"

    # Decision
    base_priority, hit_term = _decide(_sum, _st, _ex, feature_name)

    # Crashlytics log → keep current priority
    if base_priority == "KEEP":
        kept = current_priority or "Medium"
        return (
            kept,
            is_scoped,
            scope_type,
            scope_detail,
            "Crashlytics log dump — current priority kept, manual review recommended.",
            ""
        )

    reason = REASON_MAP[base_priority]
    if hit_term:
        reason += f' · Signal: "{hit_term}"'

    priority      = base_priority
    adjusted_note = ""

    # Frequency adjustment
    freq_drop = FREQ_DROPS.get(freq, 0)
    if freq_drop > 0:
        idx     = PRIORITY_ORDER.index(priority)
        new_idx = min(idx + freq_drop, len(PRIORITY_ORDER) - 1)

        # Never drop true Gating below Medium by frequency alone
        if base_priority == "Gating":
            new_idx = min(new_idx, PRIORITY_ORDER.index("Medium"))

        if new_idx != idx:
            old_p    = priority
            priority = PRIORITY_ORDER[new_idx]
            adjusted_note += (
                f"📉 Frequency: {FREQ_LABELS[freq]} — dropped {old_p} → {priority}. "
            )

    # Device scope adjustment
    if is_scoped:
        flagship = ["iphone", "samsung galaxy s", "pixel", "flagship", "ipad"]
        is_flagship = (
            any(s in combo for s in flagship) or
            any(s in scope_detail.lower() for s in flagship)
        )

        if not is_flagship:
            idx = PRIORITY_ORDER.index(priority)
            if idx < len(PRIORITY_ORDER) - 1:
                old_p    = priority
                priority = PRIORITY_ORDER[idx + 1]
                adjusted_note += (
                    f"📱 Device scope: {scope_detail} — "
                    f"dropped {old_p} → {priority}. "
                    f"Escalate if confirmed on other devices."
                )
        else:
            adjusted_note += (
                f"📱 Device scope: {scope_detail} — "
                f"high-adoption device, priority kept at {priority}."
            )

    if PRIORITY_ORDER.index(priority) > PRIORITY_ORDER.index("Low"):
        priority = "Low"

    return priority, is_scoped, scope_type, scope_detail, reason, adjusted_note


def stp_priority_from_text(text: str, feature_name: str = "") -> Tuple[str, str]:
    """Backward compatibility helper."""
    return _decide(text, "", "", feature_name)
 
def stp_priority_from_text(text: str, feature_name: str = "") -> Tuple[str, str]:
    """Backwards compat."""
    return _decide(text, "", "", feature_name)
 
