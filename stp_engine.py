"""
STP Engine — BiP QA priority assignment.
 
Core logic: eski STP_REBALANCE_REPORT algoritması —
  gating_terms / high_terms / medium_terms keyword seti,
  feature name'e göre extension'lar.
 
Eklentiler (orijinal kodda olmayan, korunan):
  - Word boundary matching (hang → herhangi false positive önlenir)
  - Description parsing (actual/expected/steps ayrıştırılır)
  - Reproduce frequency adjustment
  - Device/OS scope adjustment
  - detect_device_os_scope (app.py Tab1 için)
"""
 
import re
from typing import Tuple
 
PRIORITY_ORDER = ["Gating", "High", "Medium", "Low"]
 
REASON_MAP = {
    "Gating": "Core functionality broken — blocks release. Must fix before shipping.",
    "High":   "Core feature validation — important feature affected, fix within 2 weeks.",
    "Medium": "UX / secondary behaviour — workaround exists, fix within 6 weeks.",
    "Low":    "Edge validation / cosmetic — no functional impact.",
}
 
FREQ_OPTIONS = ["always", "frequently", "occasionally", "rarely", "once"]
 
FREQ_DROPS = {
    "always":       0,
    "frequently":   0,
    "occasionally": 1,
    "rarely":       1,
    "once":         2,
}
 
FREQ_LABELS = {
    "always":       "Always reproducible",
    "frequently":   "Frequently reproducible",
    "occasionally": "Occasionally reproducible",
    "rarely":       "Rarely reproducible",
    "once":         "Reproduced once",
}
 
 
# ═══════════════════════════════════════════════════════════════
# Exported term lists (app.py keyword chip display için)
# ═══════════════════════════════════════════════════════════════
 
GATING_TERMS = [
    "crash", "freeze", "hang", "stuck",
    "cannot open", "can't open", "not open",
    "cannot send", "can't send", "message not sent",
    "cannot receive", "can't receive",
    "login fail", "cannot login",
    "cannot start call", "call not started", "cannot call",
    "force close", "fatal error", "anr", "not responding",
    "çöküyor", "çöktü", "donuyor", "takılıyor",
    "açılmıyor", "gönderilemiyor", "alınamıyor",
    "giriş yapılamıyor",
]
 
HIGH_TERMS = [
    "send message", "message sent",
    "receive message", "message received",
    "voice call", "video call", "call started",
    "incoming call", "outgoing call",
    "send emoji", "emoji sent",
    "send sticker", "sticker sent",
    "reaction", "delivered", "message delivered",
]
 
MEDIUM_TERMS = [
    "search", "category", "panel", "picker",
    "keyboard", "tab", "icon", "scroll",
    "display", "shown", "settings",
    "profile", "notification", "ui",
    "history", "log", "list", "filter",
    "duration", "timer", "preview", "thumbnail",
    "menu", "navigate", "view", "layout", "spacing",
    "gap", "alignment",
]
 
LOW_COSMETIC_TERMS = [
    "typo", "spelling", "alignment issue", "color wrong",
    "wrong font", "wrong icon", "wrong spacing",
    "animation glitch", "transition issue",
    "placeholder", "tooltip", "padding",
    "recommendation", "suggestion", "öneri",
]
 
HARD_CRASH_TERMS = [
    "crash", "crashes", "crashed", "force close",
    "fatal error", "anr", "not responding",
    "çöküyor", "çöktü", "kapanıyor",
]
 
FREEZE_TERMS = [
    "freeze", "frozen", "hang", "hangs", "hung",
    "stuck", "unresponsive",
    "donuyor", "dondu", "takılıyor", "takıldı",
]
 
 
# ═══════════════════════════════════════════════════════════════
# Keyword sets — eski algoritma mantığı + feature extensions
# ═══════════════════════════════════════════════════════════════
 
def get_keyword_sets(feature_name: str):
    """
    Eski STP_REBALANCE_REPORT.py'deki get_keyword_sets fonksiyonu.
    Base set + feature name'e göre minimal extension.
    """
    gating = [
        "crash", "freeze", "hang", "stuck",
        "cannot open", "can't open", "not open",
        "cannot send", "can't send", "message not sent",
        "cannot receive", "can't receive",
        "login fail", "cannot login",
        "cannot start call", "call not started", "cannot call",
        "force close", "fatal error", "anr", "not responding",
        "çöküyor", "çöktü", "donuyor", "takılıyor",
        "açılmıyor", "gönderilemiyor", "alınamıyor",
        "giriş yapılamıyor",
    ]
 
    high = [
        "send message", "message sent",
        "receive message", "message received",
        "voice call", "video call", "call started",
        "incoming call", "outgoing call",
        "send emoji", "emoji sent",
        "send sticker", "sticker sent",
        "reaction", "delivered", "message delivered",
    ]
 
    medium = [
        "search", "category", "panel", "picker",
        "keyboard", "tab", "icon", "scroll",
        "display", "shown", "settings",
        "profile", "notification", "ui",
        "history", "log", "list", "filter",
        "duration", "timer", "preview", "thumbnail",
        "menu", "navigate", "view", "layout", "spacing",
        "gap", "alignment",
    ]
 
    fn = feature_name.lower() if feature_name else ""
 
    if "call" in fn:
        gating += ["cannot receive call", "cannot make call"]
        high   += ["call connected", "call established", "call answered", "call ended"]
        medium += ["call history"]
 
    elif "chat" in fn:
        gating += [
            "cannot open chat", "chat not open",
            "cannot send message", "cannot receive message",
            "chat not load", "cannot load chat",
        ]
        high += [
            "message delivered", "message seen",
            "delete message", "edit message",
            "reply message", "forward message",
        ]
        medium += ["chat list", "open conversation"]
 
    elif "channel" in fn:
        gating += ["cannot open channel", "channel not open"]
        high   += ["channel post", "post sent", "share", "subscribe", "unsubscribe", "join channel"]
 
    elif "status" in fn or "story" in fn:
        gating += [
            "cannot view status", "status not open",
            "cannot share status", "cannot upload status",
        ]
        high += [
            "share status", "status shared", "status uploaded",
            "view status", "status displayed", "status seen",
            "delete status", "status deleted",
        ]
        medium += ["status list"]
 
    elif "more" in fn or "other" in fn:
        gating += ["cannot logout", "cannot load", "not load", "app not open"]
        high   += [
            "settings saved", "settings changed", "profile updated",
            "logout success", "login success",
            "notification received", "notification sent",
            "change password", "privacy change", "privacy updated",
        ]
        medium += ["open settings", "select"]
 
    elif "emoji" in fn or "sticker" in fn:
        gating += ["emoji not sent", "cannot react"]
        high   += ["react", "postback"]
        medium += ["recent", "favorites", "favourite", "skin tone"]
 
    return gating, high, medium
 
 
# ═══════════════════════════════════════════════════════════════
# Matching — word boundary for short single words
# ═══════════════════════════════════════════════════════════════
 
def _match(text: str, term: str) -> bool:
    """
    Multi-word phrases  → basit substring.
    Tek kısa kelimeler (≤6 char) → word boundary
      (hang → herhangi, log → dialog gibi false match önlenir).
    Tek uzun kelimeler (>6 char) → substring (yeterince özgül).
    """
    if " " in term:
        return term in text
    if len(term) <= 6:
        return bool(re.search(
            r"(?<![a-zA-Z\u00c0-\u024f])" + re.escape(term) + r"(?![a-zA-Z\u00c0-\u024f])",
            text
        ))
    return term in text
 
 
def _find_hit(text: str, terms: list):
    """İlk eşleşen terimi döndür, yoksa None."""
    for t in terms:
        if _match(text, t):
            return t
    return None
 
 
def stp_priority_from_text(text: str, feature_name: str = "") -> Tuple[str, str]:
    """
    Eski algoritma: gating → high → medium → low cascade.
    Returns (priority, hit_term).
    """
    gating, high, medium = get_keyword_sets(feature_name)
 
    hit = _find_hit(text, gating)
    if hit:
        return "Gating", hit
 
    hit = _find_hit(text, high)
    if hit:
        return "High", hit
 
    hit = _find_hit(text, medium)
    if hit:
        return "Medium", hit
 
    return "Low", ""
 
 
# ═══════════════════════════════════════════════════════════════
# Device / OS scope detection (Tab1 PreReview için)
# ═══════════════════════════════════════════════════════════════
 
DEVICE_PATTERNS = [
    r"\bredmi\s*\d+\b", r"\bxiaomi\b", r"\bsamsung\s+[a-z]\d+", r"\bhuawei\b",
    r"\biphone\s*\d+", r"\bpixel\s*\d+", r"\boneplus\b", r"\boppo\b",
    r"\brealme\b", r"\bvivo\b", r"\bnokia\b", r"\bpoco\b",
    r"\bmoto\b", r"\bmotorola\b", r"\bgalaxy\s+[a-z]\d+",
]
 
OS_PATTERNS = [
    r"\bandroid\s*\d+", r"\bios\s*\d+", r"\bmiui\s*\d+",
    r"\bone\s*ui\s*\d+", r"\bharmonyos\b", r"\bcoloros\b",
    r"\bandroid\s+1[0-9]\b", r"\bandroid\s+[89]\b",
]
 
CHIPSET_PATTERNS = [
    r"\bsnapdragon\s*\d+", r"\bexynos\s*\d+", r"\bdimensity\s*\d+",
    r"\bkirin\s*\d+", r"\ba\d+\s*chip\b", r"\bbionic\b",
    r"\bmediatek\b", r"\bhelio\b",
]
 
 
def detect_device_os_scope(text: str) -> Tuple[bool, str, str]:
    t = text.lower()
    for pat in CHIPSET_PATTERNS:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            return True, "chipset", m.group(0)
    for pat in OS_PATTERNS:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            return True, "os_version", m.group(0)
    device_matches = []
    for pat in DEVICE_PATTERNS:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            device_matches.append(m.group(0))
    if len(device_matches) == 1:
        return True, "single_device_repro", device_matches[0]
    if len(device_matches) > 1:
        return True, "device", ", ".join(device_matches[:2])
    return False, "", ""
 
 
# ═══════════════════════════════════════════════════════════════
# Public API — app.py'nin kullandığı tek fonksiyon
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
) -> Tuple[str, bool, str, str, str, str]:
    """
    Returns (priority, is_scoped, scope_type, scope_detail, reason, adjusted_note)
 
    Core logic:
      1. Tüm alanları birleştir (summary + steps + actual + expected)
      2. Eski algoritma: gating → high → medium → low keyword cascade
      3. Reproduce frequency ile priority düşür (occasionally/rarely/once)
      4. Device scope ile priority düşür (non-flagship)
    """
    # ── Girdi normalize ──────────────────────────────────────
    _summary  = (summary or text or "").strip()
    _steps    = (steps or actual_result or "").strip()
    _expected = (expected_result or "").strip()
 
    combined = (_summary + " " + _steps + " " + _expected).lower()
 
    # ── Device / OS scope ────────────────────────────────────
    auto_scoped, auto_scope_type, auto_scope_detail = detect_device_os_scope(combined)
    if device_scope.strip():
        is_scoped    = True
        scope_type   = "manual"
        scope_detail = device_scope.strip()
    else:
        is_scoped    = auto_scoped
        scope_type   = auto_scope_type
        scope_detail = auto_scope_detail
 
    # ── Frequency normalize ──────────────────────────────────
    freq = (reproduce_frequency or "always").lower().strip()
    if freq not in FREQ_OPTIONS:
        freq = "always"
 
    # ── Core priority kararı (eski algoritma) ────────────────
    base_priority, hit_term = stp_priority_from_text(combined, feature_name)
 
    if hit_term:
        reason = f"{REASON_MAP[base_priority]} · Matched: \"{hit_term}\""
    else:
        reason = REASON_MAP[base_priority]
 
    priority      = base_priority
    adjusted_note = ""
 
    # ── Step 1: Frequency adjustment ─────────────────────────
    freq_drop  = FREQ_DROPS.get(freq, 0)
    freq_label = FREQ_LABELS.get(freq, freq)
 
    if freq_drop > 0:
        idx     = PRIORITY_ORDER.index(priority)
        new_idx = min(idx + freq_drop, len(PRIORITY_ORDER) - 1)
 
        # Gating bug'lar "once" ile bile Medium'dan aşağı inmez
        if base_priority == "Gating":
            new_idx = min(new_idx, PRIORITY_ORDER.index("Medium"))
 
        if new_idx != idx:
            old_p    = priority
            priority = PRIORITY_ORDER[new_idx]
            adjusted_note += (
                f"📉 Frequency: {freq_label} — "
                f"dropped {old_p} → {priority}. "
            )
 
    # ── Step 2: Device scope adjustment ─────────────────────
    if is_scoped:
        flagship_signals = ["iphone", "samsung galaxy s", "pixel", "flagship", "ipad"]
        is_flagship = (
            any(s in combined for s in flagship_signals) or
            any(s in scope_detail.lower() for s in flagship_signals)
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
 
    # ── Floor: asla Low'dan aşağı ────────────────────────────
    if PRIORITY_ORDER.index(priority) > PRIORITY_ORDER.index("Low"):
        priority = "Low"
 
    return priority, is_scoped, scope_type, scope_detail, reason, adjusted_note
 
