"""
STP Engine — BiP QA priority assignment.
 
QA perspektifi:
  GATING  = crash / freeze / stuck / core flow tamamen broken
             CLONE olsa da, specific feature olsa da crash = Gating
  HIGH    = functional bug — feature çalışıyor ama yanlış sonuç
             (not displayed, error, incorrect, missing, wrong data)
  MEDIUM  = UX / secondary behaviour — visual glitch, ordering, minor
  LOW     = saf cosmetic — typo, color, spacing, alignment
  Default = Medium (keyword yoksa functional scenario varsayılır)
"""
 
import re
from typing import Tuple
 
PRIORITY_ORDER = ["Gating", "High", "Medium", "Low"]
 
REASON_MAP = {
    "Gating": "App crash / freeze / core flow broken — blocks release. Must fix before shipping.",
    "High":   "Functional bug — feature behaves incorrectly. Fix within 2 weeks.",
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
# GATING — crash, freeze, core fail
# QA kuralı: crash her zaman Gating. CLONE/specific feature fark etmez.
# ═══════════════════════════════════════════════════════════════
GATING_TERMS = [
    # Crash — her context'te Gating
    "crash", "crashes", "crashed", "force close",
    "fatal error", "anr", "not responding",
    "çöküyor", "çöktü", "kapanıyor", "uygulama kapandı",
    # Freeze / stuck — her context'te Gating
    "freeze", "frozen", "hang", "hangs", "hung",
    "stuck", "unresponsive",
    "donuyor", "dondu", "takılıyor", "takıldı",
    "askıda", "yanıt vermiyor",
    # Core open fail
    "cannot open", "can't open", "cant open", "won't open",
    "unable to open", "fails to open", "app not opening",
    "açılmıyor", "açılamıyor", "girilemiyor",
    # Core send fail
    "cannot send", "can't send", "message not sent", "failed to send",
    "unable to send", "send failed",
    "gönderilemiyor", "gönderilemedi",
    # Core receive fail
    "cannot receive", "can't receive", "messages not delivered",
    "alınamıyor", "iletilmiyor",
    # Login fail
    "cannot login", "can't login", "login fail", "login failed",
    "cannot sign in", "unable to login",
    "giriş yapılamıyor", "oturum açılamıyor",
    # Call fail
    "cannot start call", "call not started", "cannot call",
    "cannot make call", "cannot receive call",
]
 
# ═══════════════════════════════════════════════════════════════
# HIGH — functional bug, wrong behaviour
# ═══════════════════════════════════════════════════════════════
HIGH_TERMS = [
    # Wrong / incorrect behaviour
    "not displayed", "not showing", "not shown",
    "not appearing", "not appear", "not visible",
    "not working", "does not work", "doesn't work",
    "not loading", "does not load", "doesn't load",
    "not updating", "does not update", "doesn't update",
    "not removing", "does not remove", "not removed",
    "not detecting", "not detected",
    "not redirecting", "does not redirect",
    # Error signals
    "error occurs", "shows error", "error message", "gives error",
    "incorrect", "wrong data", "wrong result",
    # Missing / lost data
    "missing", "disappears", "disappeared",
    "blank message", "appears blank", "empty message",
    "unable to", "fails to",
    # Core action validation (başarılı senaryo testi)
    "send message", "message sent",
    "receive message", "message received",
    "voice call", "video call", "call started",
    "incoming call", "outgoing call",
    "send emoji", "emoji sent",
    "send sticker", "sticker sent",
    "reaction", "delivered", "message delivered",
    # Performance / response issues
    "slowness", "slow", "slow loading", "no response", "not responding",
    "lag", "performance issue",
    # Incorrect behaviour (no explicit error word)
    "does not change", "does not close", "does not end", "does not stop",
    "does not delete", "does not clear", "does not save",
    "not deleted", "not closed", "not ended", "not stopped",
    "still active", "still visible", "still showing", "remains active",
    "duplicate", "duplicated", "sent twice",
    "wrong name", "wrong label", "wrong text", "wrong screen",
    "incorrect result", "incorrect data",
    # Turkish
    "görünmüyor", "çalışmıyor", "hatalı", "yanlış göster",
    "kayboldu", "boş görün", "yavaş", "geç",
]
 
# ═══════════════════════════════════════════════════════════════
# MEDIUM — UX, secondary, non-blocking
# ═══════════════════════════════════════════════════════════════
MEDIUM_TERMS = [
    "search", "category", "panel", "picker",
    "keyboard", "tab", "icon", "scroll",
    "display", "shown", "settings",
    "profile", "notification", "ui",
    "history", "log", "list", "filter",
    "duration", "timer", "preview", "thumbnail",
    "menu", "navigate", "view", "layout", "spacing",
    "gap", "alignment",
    "overlap", "overlapped", "overlapping",
    "flicker", "flickering", "blink", "blinking",
    "order", "ordering", "sorted", "alphabetical",
    "position", "smooth", "smoothly",
]
 
# ═══════════════════════════════════════════════════════════════
# LOW — pure cosmetic
# ═══════════════════════════════════════════════════════════════
LOW_COSMETIC_TERMS = [
    "typo", "spelling", "color wrong", "colour wrong",
    "wrong font", "wrong icon", "wrong spacing", "padding",
    "animation glitch", "transition issue",
    "placeholder text", "tooltip", "margin",
    "recommendation", "suggestion", "öneri",
    "readable", "readability",
    "format difference", "alignment issue", "misaligned",
    "truncated", "cut off", "last character missing",
    "dark mode color", "ui format",
]
 
# App.py alias exports
HARD_CRASH_TERMS = [
    "crash", "crashes", "crashed", "force close",
    "fatal error", "anr", "not responding",
    "çöküyor", "çöktü", "kapanıyor",
]
FREEZE_TERMS = [
    "freeze", "frozen", "hang", "hangs", "stuck", "unresponsive",
    "donuyor", "dondu", "takılıyor", "takıldı",
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
        m += ["call history"]
    elif "chat" in fn:
        g += ["cannot open chat", "chat not open", "cannot send message",
              "cannot receive message", "chat not load", "cannot load chat"]
        h += ["message delivered", "message seen", "delete message",
              "edit message", "reply message", "forward message"]
        m += ["chat list", "open conversation"]
    elif "channel" in fn:
        g += ["cannot open channel", "channel not open"]
        h += ["channel post", "post sent", "subscribe", "unsubscribe", "join channel"]
    elif "status" in fn or "story" in fn:
        g += ["cannot view status", "status not open",
              "cannot share status", "cannot upload status"]
        h += ["share status", "status shared", "status uploaded",
              "view status", "status displayed", "status seen",
              "delete status", "status deleted"]
        m += ["status list"]
    elif "more" in fn or "other" in fn:
        g += ["cannot logout", "cannot load", "not load", "app not open"]
        h += ["settings saved", "settings changed", "profile updated",
              "logout success", "login success", "notification received",
              "notification sent", "change password", "privacy change", "privacy updated"]
        m += ["open settings", "select"]
    elif "emoji" in fn or "sticker" in fn:
        g += ["emoji not sent", "cannot react"]
        h += ["react", "postback"]
        m += ["recent", "favorites", "favourite", "skin tone"]
    return g, h, m
 
# ═══════════════════════════════════════════════════════════════
# Matching — word boundary for short single words
# ═══════════════════════════════════════════════════════════════
def _match(text: str, term: str) -> bool:
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
    return None
 
# ═══════════════════════════════════════════════════════════════
# Core vs Secondary feature classifier
# ═══════════════════════════════════════════════════════════════
 
# BiP'in CORE fonksiyonları — bunlar etkilenirse Gating
CORE_FEATURE_TERMS = [
    # Mesajlaşma
    "message", "chat", "send", "receive", "inbox",
    "mesaj", "sohbet", "gönder",
    # Arama
    "call", "voice", "video call", "arama", "sesli", "görüntülü",
    # Login / auth
    "login", "sign in", "otp", "authentication",
    "giriş", "oturum",
    # App genel açılış
    "app launch", "app open", "on launch", "on startup",
    "uygulama aç",
]
 
# SECONDARY feature'lar — crash olsa bile Gating değil, High
SECONDARY_FEATURE_TERMS = [
    # Media / 3rd party
    "youtube", "video player", "gif", "sticker market",
    "rich link", "link preview", "image download",
    # Discovery / channels
    "discover", "ddm", "channel info", "meb channel",
    "explore", "keşfet",
    # Live location
    "live location", "location sharing", "canlı konum",
    # Polls / surveys (core olmayan)
    "poll", "survey", "anket",
    # Theme / UI settings
    "theme", "dark mode", "tema",
    # Disappearing messages
    "disappearing", "kaybolan mesaj",
    # Stories / status
    "story", "status", "hikaye", "durum",
    # Paycell / payment (3rd party)
    "paycell", "payment", "wallet",
    # Temiz Gol / external apps
    "temiz gol",
]
 
def _is_secondary_feature(summary: str) -> bool:
    """Summary secondary feature içeriyor mu?"""
    s = summary.lower()
    return any(t in s for t in SECONDARY_FEATURE_TERMS)
 
def _has_core_feature(summary: str) -> bool:
    """Summary core BiP feature içeriyor mu?"""
    s = summary.lower()
    return any(t in s for t in CORE_FEATURE_TERMS)
 
 
# ═══════════════════════════════════════════════════════════════
# Crashlytics log dump detector
# ═══════════════════════════════════════════════════════════════
def _is_crashlytics_log(summary: str) -> bool:
    """
    'Crashlytics - stack trace' gibi log dump'lar — crash sinyali değil,
    sadece izleme kaydı. Mevcut priority korunur.
    """
    s = summary.lower().strip()
    return bool(re.match(r'^crashlytics\s*[\-|]', s))
 
# ═══════════════════════════════════════════════════════════════
# Core decision
# ═══════════════════════════════════════════════════════════════
def _decide(summary: str, steps: str, expected: str,
            feature_name: str = "") -> Tuple[str, str]:
    """
    Priority + hit term.
    Önce summary, sonra steps/expected.
    Crashlytics log dump → None (caller mevcut priority'yi korur).
    """
    # Crashlytics log dump — priority kararı veremeyiz
    if _is_crashlytics_log(summary):
        return "KEEP", "crashlytics_log"
 
    eg, eh, em = _feature_extensions(feature_name)
    all_g = GATING_TERMS + eg
    all_h = HIGH_TERMS   + eh
    all_m = MEDIUM_TERMS + em
 
    s  = summary.lower()
    se = (steps + " " + expected).lower()
 
    # ── Low: cosmetic keyword var, failure sinyali yok ────────
    low_hit = _hit(s, LOW_COSMETIC_TERMS)
    has_failure_in_s = bool(_hit(s, all_g) or _hit(s, all_h))
    if low_hit and not has_failure_in_s:
        return "Low", low_hit
 
    # ── Gating: summary ───────────────────────────────────────
    hit = _hit(s, all_g)
    if hit:
        # Crash/freeze için context kontrolü:
        # Core feature etkileniyorsa → Gating
        # Secondary feature etkileniyorsa → High
        CRASH_FREEZE_SET = {
            "crash", "crashes", "crashed", "force close",
            "fatal error", "anr", "not responding",
            "freeze", "frozen", "hang", "hangs", "hung",
            "stuck", "unresponsive",
            "çöküyor", "çöktü", "kapanıyor",
            "donuyor", "dondu", "takılıyor", "takıldı",
        }
        is_crash_or_freeze = hit in CRASH_FREEZE_SET
 
        if is_crash_or_freeze and _is_secondary_feature(summary):
            # Secondary feature crash → High, Gating değil
            return "High", f"secondary-feature crash: {hit}"
        elif is_crash_or_freeze and not _has_core_feature(summary):
            # Bağlam belirsiz ama core değil → High (conservative)
            return "High", f"non-core crash: {hit}"
        else:
            return "Gating", hit
 
    # ── High: summary ─────────────────────────────────────────
    hit = _hit(s, all_h)
    if hit:
        return "High", hit
 
    # ── Medium: summary ───────────────────────────────────────
    hit = _hit(s, all_m)
    if hit:
        return "Medium", hit
 
    # ── Steps / Expected (description parse) ──────────────────
    if se.strip():
        hit = _hit(se, all_g)
        if hit:
            return "Gating", f"desc: {hit}"
        hit = _hit(se, all_h)
        if hit:
            return "High", f"desc: {hit}"
        hit = _hit(se, all_m)
        if hit:
            return "Medium", f"desc: {hit}"
 
    # ── Default ───────────────────────────────────────────────
    return "Medium", ""
 
# ═══════════════════════════════════════════════════════════════
# Device / OS scope
# ═══════════════════════════════════════════════════════════════
DEVICE_PATTERNS  = [
    r"\bredmi\s*\d+\b", r"\bxiaomi\b", r"\bsamsung\s+[a-z]\d+", r"\bhuawei\b",
    r"\biphone\s*\d+", r"\bpixel\s*\d+", r"\boneplus\b", r"\boppo\b",
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
    t = text.lower()
    for pat in CHIPSET_PATTERNS:
        m = re.search(pat, t, re.IGNORECASE)
        if m: return True, "chipset", m.group(0)
    for pat in OS_PATTERNS:
        m = re.search(pat, t, re.IGNORECASE)
        if m: return True, "os_version", m.group(0)
    matches = []
    for pat in DEVICE_PATTERNS:
        m = re.search(pat, t, re.IGNORECASE)
        if m: matches.append(m.group(0))
    if len(matches) == 1: return True, "single_device_repro", matches[0]
    if len(matches) > 1:  return True, "device", ", ".join(matches[:2])
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
    Returns (priority, is_scoped, scope_type, scope_detail, reason, adjusted_note)
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
    if freq not in FREQ_OPTIONS: freq = "always"
 
    # Decision
    base_priority, hit_term = _decide(_sum, _st, _ex, feature_name)
 
    # Crashlytics log → mevcut priority koru
    if base_priority == "KEEP":
        kept = current_priority or "Medium"
        return (kept, is_scoped, scope_type, scope_detail,
                "Crashlytics log dump — mevcut priority korundu, manuel inceleme önerilir.",
                "")
 
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
    """Backwards compat."""
    return _decide(text, "", "", feature_name)
 
def stp_priority_from_text(text: str, feature_name: str = "") -> Tuple[str, str]:
    """Backwards compat."""
    return _decide(text, "", "", feature_name)
 
