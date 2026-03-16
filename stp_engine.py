"""
STP Engine — BiP QA priority assignment.
 
Architecture: 3-stage cascade (mirrors the spec's decision tree):
  Stage 1 → Is Gating?   (hard failure / core broken / crash)
  Stage 2 → Is High?     (core business action, feature-level validation)
  Stage 3 → Medium vs Low (UX/navigation vs edge/cosmetic)
 
Feature groups (per spec):
  A. Failure intensity   — has_crash, has_open_fail, has_send_fail, etc.
  B. Core action         — has_send_action, has_receive_action, has_call_action, etc.
  C. UX / navigation     — has_search, has_list, has_display, etc.
  D. Repo/feature context — feature_area (chat/calls/channels/status/emoji/more)
  E. Field-aware weight  — same token scores differently in Summary vs Steps vs Expected
"""
 
import re
from typing import Tuple, Dict
 
PRIORITY_ORDER = ["Gating", "High", "Medium", "Low"]
 
# ═══════════════════════════════════════════════════════════════
# A. FAILURE INTENSITY TERMS  (Stage 1 — Gating triggers)
# ═══════════════════════════════════════════════════════════════
 
# Hard failure: app/feature completely non-functional
OPEN_FAIL_TERMS = [
    "cannot open", "can't open", "cant open", "not open", "won't open",
    "açılmıyor", "açılamıyor", "girilemiyor", "app not opening",
    "unable to open", "fails to open", "doesn't open",
]
 
SEND_FAIL_TERMS = [
    "cannot send", "can't send", "cant send", "message not sent",
    "failed to send", "send failed", "sending failed", "unable to send",
    "gönderilemiyor", "gönderme başarısız", "gönderilemedi", "gönderme çalışmıyor",
    "mesaj atılamıyor", "mesaj iletilmiyor",
]
 
RECEIVE_FAIL_TERMS = [
    "cannot receive", "can't receive", "not received", "not delivering",
    "messages not delivered", "message not arriving", "unable to receive",
    "alınamıyor", "gelmiyor", "iletilmiyor", "ulaşmıyor",
]
 
LOGIN_FAIL_TERMS = [
    "cannot login", "can't login", "login fail", "login fails", "login failed",
    "sign in fail", "cannot sign in", "unable to login", "authentication failed",
    "verification failed", "otp gelmiyor", "otp çalışmıyor", "otp not received",
    "giriş yapılamıyor", "giriş olunmuyor", "oturum açılamıyor",
    "kayıt olunamıyor", "doğrulama başarısız",
]
 
CALL_FAIL_TERMS = [
    "cannot call", "can't call", "call not started", "call fails", "call failed",
    "cannot make call", "call not working", "call not connecting", "call not starting",
    "not starting", "call won't start", "unable to call", "unable to start call",
    "voice call broken", "video call broken", "call not initiated",
    "arama yapılamıyor", "arama başlatılamıyor", "arama çalışmıyor",
    "sesli arama çalışmıyor", "görüntülü arama çalışmıyor",
    "arama başlatılamadı", "aramaya bağlanılamıyor",
]
 
STATUS_FAIL_TERMS = [
    "cannot view status", "status not open", "cannot share status",
    "cannot upload status", "status upload fail", "status not loading",
    "durum paylaşılamıyor", "durum açılmıyor", "hikaye yüklenemiyor",
    "story not uploading", "cannot post story", "story upload fail",
]
 
CHANNEL_FAIL_TERMS = [
    "cannot open channel", "channel not open", "channel not loading",
    "cannot access channel", "channel access broken",
    "kanal açılmıyor", "kanala girilemiyor",
]
 
CRASH_TERMS = [
    "crash", "crashes", "crashed", "force close", "app closed unexpectedly",
    "fatal error", "anr", "not responding", "black screen",
    "çöküyor", "çöktü", "kapanıyor", "uygulama kapandı",
]
 
FREEZE_STUCK_TERMS = [
    "freeze", "frozen", "hang", "hangs", "hung", "stuck", "unresponsive",
    "donuyor", "dondu", "takılıyor", "takıldı", "yanıt vermiyor",
    "askıda", "ekran dondu",
]
 
LOAD_FAIL_TERMS = [
    "cannot load", "fails to load", "loading failed", "not loading",
    "load error", "yüklenemiyor", "yükleme başarısız",
]
 
FRAUD_TERMS = [
    "fraud", "unauthorized charge", "billing error", "payment error",
    "maddi kayıp", "ücretlendirme hatası", "faturalama hatası",
    "para çekildi", "ödeme hatası", "yanlış fatura",
]
 
DATA_LOSS_TERMS = [
    "data loss", "data corruption", "permanent data loss",
    "messages lost", "messages deleted", "veri kaybı",
    "kalıcı veri kaybı", "mesajlar silindi",
]
 
# ═══════════════════════════════════════════════════════════════
# B. CORE BUSINESS ACTION TERMS  (Stage 2 — High triggers)
# ═══════════════════════════════════════════════════════════════
 
SEND_ACTION_TERMS = [
    "send message", "sent message", "message sent", "message delivered",
    "message received", "receive message", "received message",
    "reply message", "forward message", "edit message", "delete message",
    "seen", "delivered", "read receipt",
    "mesaj gönder", "mesaj gönderilebiliyor", "mesaj alındı",
]
 
CALL_ACTION_TERMS = [
    "voice call", "video call", "incoming call", "outgoing call",
    "call connected", "call established", "call answered", "call ended",
    "call initiated", "call received", "audio call", "group call",
    "sesli arama", "görüntülü arama", "arama bağlandı", "arama kuruldu",
    "arama cevaplandı", "arama sonlandı", "gelen arama", "giden arama",
]
 
STATUS_ACTION_TERMS = [
    "share status", "upload status", "status uploaded", "status shared",
    "view status", "status viewed", "delete status", "status deleted",
    "add status", "status visible", "watch status",
    "durum paylaş", "durum yükle", "durum görüntüle", "durum sil",
]
 
CHANNEL_ACTION_TERMS = [
    "channel post", "post sent", "subscribe", "unsubscribe",
    "join channel", "leave channel", "channel joined", "channel created",
    "kanal gönder", "kanala katıl", "abone ol", "abonelikten çık",
]
 
REACTION_ACTION_TERMS = [
    "reaction", "react", "emoji sent", "emoji send", "sticker sent",
    "sticker send", "send emoji", "send sticker",
    "tepki", "tepki ekle", "emoji gönder", "stiker gönder",
]
 
PROFILE_ACTION_TERMS = [
    "profile updated", "settings saved", "password changed",
    "privacy changed", "notification received", "push received",
    "logout success", "login success",
    "profil güncellendi", "ayarlar kaydedildi", "çıkış yapıldı",
    "bildirim alındı",
]
 
NOTIFICATION_ACTION_TERMS = [
    "notification received", "notification sent", "push notification",
    "badge updated", "notification shown",
    "bildirim geldi", "bildirim gönderildi", "push bildirim",
]
 
# ═══════════════════════════════════════════════════════════════
# C. UX / NAVIGATION TERMS  (Stage 3 — Medium triggers)
# ═══════════════════════════════════════════════════════════════
 
SEARCH_TERMS = [
    "search", "search bar", "search results", "search icon",
    "arama", "arama çubuğu", "arama sonuçları",
]
 
LIST_DISPLAY_TERMS = [
    "list", "listed", "display", "displayed", "shown", "shows", "view",
    "scroll", "scrollable", "scrolled",
    "liste", "listeleniyor", "görüntüleniyor", "gösteriliyor",
]
 
FILTER_TERMS = [
    "filter", "filtered", "sort", "sorted", "category", "categories",
    "filtre", "filtreleme", "sırala", "kategori",
]
 
NAVIGATION_TERMS = [
    "navigate", "navigation", "tab", "icon", "panel", "open panel",
    "menu", "settings", "open settings", "select", "picker", "keyboard",
    "sekme", "ikon", "panel aç", "menü", "ayarlar aç", "seç",
]
 
HISTORY_LOG_TERMS = [
    "history", "log", "timer", "duration", "timestamp",
    "geçmiş", "kayıt", "süre", "zamanlayıcı", "zaman damgası",
]
 
PREVIEW_TERMS = [
    "preview", "thumbnail", "preview shown", "thumbnail shown",
    "önizleme", "küçük resim", "önizleme gösteriliyor",
]
 
PROFILE_DISPLAY_TERMS = [
    "profile", "profile page", "profile view", "profile screen",
    "profil", "profil sayfası", "profil görüntüle",
]
 
SETTINGS_DISPLAY_TERMS = [
    "settings", "settings page", "settings screen", "open settings",
    "ayarlar", "ayarlar sayfası", "ayarlar ekranı",
]
 
EMOJI_UI_TERMS = [
    "picker", "emoji picker", "sticker picker", "recent", "favorites",
    "skin tone", "scroll emoji", "category tab",
    "seçici", "emoji seçici", "son kullanılan", "favoriler", "ten tonu",
]
 
# ═══════════════════════════════════════════════════════════════
# D. LOW / COSMETIC TERMS  (Stage 3 — Low triggers)
# ═══════════════════════════════════════════════════════════════
 
COSMETIC_TERMS = [
    "typo", "spelling", "alignment", "spacing", "padding", "margin",
    "color", "colour", "font", "icon wrong", "wrong icon",
    "wrong color", "wrong colour", "border", "shadow", "tooltip",
    "placeholder", "label wrong", "wrong label", "animation",
    "transition glitch", "blink",
    "yazım hatası", "hizalama", "renk yanlış", "ikon yanlış",
    "yanlış renk", "font sorunu", "gölge", "kenar", "animasyon bozuk",
]
 
# ═══════════════════════════════════════════════════════════════
# For UI keyword highlighting export
# ═══════════════════════════════════════════════════════════════
GATING_TERMS = (
    OPEN_FAIL_TERMS + SEND_FAIL_TERMS + RECEIVE_FAIL_TERMS +
    LOGIN_FAIL_TERMS + CALL_FAIL_TERMS + STATUS_FAIL_TERMS +
    CHANNEL_FAIL_TERMS + CRASH_TERMS + FREEZE_STUCK_TERMS +
    LOAD_FAIL_TERMS + FRAUD_TERMS + DATA_LOSS_TERMS
)
HIGH_TERMS = (
    SEND_ACTION_TERMS + CALL_ACTION_TERMS + STATUS_ACTION_TERMS +
    CHANNEL_ACTION_TERMS + REACTION_ACTION_TERMS +
    PROFILE_ACTION_TERMS + NOTIFICATION_ACTION_TERMS
)
MEDIUM_TERMS = (
    SEARCH_TERMS + LIST_DISPLAY_TERMS + FILTER_TERMS +
    NAVIGATION_TERMS + HISTORY_LOG_TERMS + PREVIEW_TERMS +
    PROFILE_DISPLAY_TERMS + SETTINGS_DISPLAY_TERMS + EMOJI_UI_TERMS
)
LOW_COSMETIC_TERMS = COSMETIC_TERMS
 
# Legacy compat
HARD_CRASH_TERMS = CRASH_TERMS
FREEZE_TERMS = FREEZE_STUCK_TERMS
 
# ═══════════════════════════════════════════════════════════════
# Device / OS scope detection
# ═══════════════════════════════════════════════════════════════
DEVICE_PATTERNS = [
    r"\bredmi\s*\d+\b", r"\bxiaomi\b", r"\bsamsung\s+[a-z]\d+\b", r"\bhuawei\b",
    r"\biphone\s*\d+\b", r"\bpixel\s*\d+\b", r"\boneplus\b", r"\boppo\b",
    r"\brealme\b", r"\bvivo\b", r"\bnokia\b", r"\blg\b",
    r"\bpoco\b", r"\bmoto\b", r"\bmotorola\b", r"\bgalaxy\s+[a-z]\d+\b",
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
 
REASON_MAP = {
    "Gating": (
        "Core function is completely broken — app/feature unusable, "
        "reproducible crash/freeze, or critical failure (fraud/data loss). "
        "Must fix before release."
    ),
    "High": (
        "Core business action is being validated (send/receive/call/share/subscribe). "
        "Feature-level risk — important for release quality. "
        "Fix within 2 weeks; PO/QA Lead to evaluate ship decision."
    ),
    "Medium": (
        "UX / navigation / data presentation scenario. "
        "Feature works but secondary behaviour or discoverability is tested. "
        "Fix within 6 weeks."
    ),
    "Low": (
        "Edge case, rare condition, cosmetic issue, or low-frequency variant. "
        "No meaningful business impact. Lowest priority."
    ),
}
 
 
# ═══════════════════════════════════════════════════════════════
# Feature extraction
# ═══════════════════════════════════════════════════════════════
 
def _has(text: str, terms: list) -> bool:
    return any(t in text for t in terms)
 
def _count(text: str, terms: list) -> int:
    return sum(1 for t in terms if t in text)
 
def extract_features(summary: str, steps: str, expected: str) -> Dict:
    """
    Extract all feature groups from the three input fields.
    Field-aware: same term weighted differently per field.
    """
    s  = summary.lower()
    st = steps.lower()
    ex = expected.lower()
    combined = s + " " + st + " " + ex
 
    # ── Failure intensity (A) ────────────────────────────────
    feats = {
        # Summary-weighted (strongest signal)
        "sum_open_fail":    _has(s,  OPEN_FAIL_TERMS),
        "sum_send_fail":    _has(s,  SEND_FAIL_TERMS),
        "sum_receive_fail": _has(s,  RECEIVE_FAIL_TERMS),
        "sum_login_fail":   _has(s,  LOGIN_FAIL_TERMS),
        "sum_call_fail":    _has(s,  CALL_FAIL_TERMS),
        "sum_status_fail":  _has(s,  STATUS_FAIL_TERMS),
        "sum_channel_fail": _has(s,  CHANNEL_FAIL_TERMS),
        "sum_crash":        _has(s,  CRASH_TERMS),
        "sum_freeze":       _has(s,  FREEZE_STUCK_TERMS),
        "sum_load_fail":    _has(s,  LOAD_FAIL_TERMS),
        # Any field
        "has_crash":        _has(combined, CRASH_TERMS),
        "has_freeze":       _has(combined, FREEZE_STUCK_TERMS),
        "has_open_fail":    _has(combined, OPEN_FAIL_TERMS),
        "has_send_fail":    _has(combined, SEND_FAIL_TERMS),
        "has_receive_fail": _has(combined, RECEIVE_FAIL_TERMS),
        "has_login_fail":   _has(combined, LOGIN_FAIL_TERMS),
        "has_call_fail":    _has(combined, CALL_FAIL_TERMS),
        "has_status_fail":  _has(combined, STATUS_FAIL_TERMS),
        "has_channel_fail": _has(combined, CHANNEL_FAIL_TERMS),
        "has_load_fail":    _has(combined, LOAD_FAIL_TERMS),
        "has_fraud":        _has(combined, FRAUD_TERMS),
        "has_data_loss":    _has(combined, DATA_LOSS_TERMS),
        # Failure count
        "failure_term_count": (
            _count(combined, CRASH_TERMS) +
            _count(combined, FREEZE_STUCK_TERMS) +
            _count(combined, OPEN_FAIL_TERMS) +
            _count(combined, SEND_FAIL_TERMS) +
            _count(combined, RECEIVE_FAIL_TERMS) +
            _count(combined, LOGIN_FAIL_TERMS) +
            _count(combined, CALL_FAIL_TERMS)
        ),
 
        # ── Core business action (B) ─────────────────────────
        "has_send_action":         _has(combined, SEND_ACTION_TERMS),
        "has_call_action":         _has(combined, CALL_ACTION_TERMS),
        "has_status_action":       _has(combined, STATUS_ACTION_TERMS),
        "has_channel_action":      _has(combined, CHANNEL_ACTION_TERMS),
        "has_reaction_action":     _has(combined, REACTION_ACTION_TERMS),
        "has_profile_action":      _has(combined, PROFILE_ACTION_TERMS),
        "has_notification_action": _has(combined, NOTIFICATION_ACTION_TERMS),
        "business_action_count": (
            _count(combined, SEND_ACTION_TERMS) +
            _count(combined, CALL_ACTION_TERMS) +
            _count(combined, STATUS_ACTION_TERMS) +
            _count(combined, CHANNEL_ACTION_TERMS) +
            _count(combined, REACTION_ACTION_TERMS)
        ),
 
        # ── UX / navigation (C) ─────────────────────────────
        "has_search":           _has(combined, SEARCH_TERMS),
        "has_list_display":     _has(combined, LIST_DISPLAY_TERMS),
        "has_filter":           _has(combined, FILTER_TERMS),
        "has_navigation":       _has(combined, NAVIGATION_TERMS),
        "has_history_log":      _has(combined, HISTORY_LOG_TERMS),
        "has_preview":          _has(combined, PREVIEW_TERMS),
        "has_profile_display":  _has(combined, PROFILE_DISPLAY_TERMS),
        "has_settings_display": _has(combined, SETTINGS_DISPLAY_TERMS),
        "has_emoji_ui":         _has(combined, EMOJI_UI_TERMS),
        "ux_term_count": (
            _count(combined, SEARCH_TERMS) +
            _count(combined, LIST_DISPLAY_TERMS) +
            _count(combined, FILTER_TERMS) +
            _count(combined, NAVIGATION_TERMS) +
            _count(combined, HISTORY_LOG_TERMS)
        ),
 
        # ── Cosmetic (D) ─────────────────────────────────────
        "has_cosmetic": _has(combined, COSMETIC_TERMS),
        "cosmetic_count": _count(combined, COSMETIC_TERMS),
 
        # ── Field lengths ────────────────────────────────────
        "summary_length":  len(s.split()),
        "steps_length":    len(st.split()),
        "expected_length": len(ex.split()),
    }
 
    # ── Feature area / repo context (D) ─────────────────────
    # Infer from summary + steps keywords
    area_signals = {
        "chat":     ["chat", "message", "sohbet", "mesaj", "conversation", "inbox"],
        "calls":    ["call", "voice", "video call", "arama", "sesli", "görüntülü"],
        "channels": ["channel", "kanal", "post", "subscribe", "unsubscribe"],
        "status":   ["status", "story", "durum", "hikaye"],
        "emoji":    ["emoji", "sticker", "reaction", "picker", "tepki", "stiker"],
        "more":     ["settings", "profile", "privacy", "password", "logout",
                     "ayarlar", "profil", "gizlilik", "şifre", "çıkış"],
    }
    area_scores = {area: sum(1 for kw in kws if kw in combined)
                   for area, kws in area_signals.items()}
    best_area = max(area_scores, key=area_scores.get) if any(area_scores.values()) else "others"
    feats["feature_area"] = best_area
    for area in area_signals:
        feats[f"repo_is_{area}"] = (best_area == area)
 
    return feats
 
 
# ═══════════════════════════════════════════════════════════════
# Cascade decision engine
# ═══════════════════════════════════════════════════════════════
 
def _stage1_is_gating(f: Dict, combined: str) -> Tuple[bool, str]:
    """
    Stage 1: Is this Gating?
    Hard failure: core function broken, crash, freeze, fraud, data loss.
    Field-aware: summary-level failures are strongest.
    """
    # Strongest: failure term IN summary — but check intermittent first
    intermit_combined = any(t in combined for t in [
        "sometimes", "occasionally", "random", "rarely", "intermittent",
        "bazen", "zaman zaman", "ara sıra", "nadir",
        "sometimes crashes", "crashes sometimes",
    ])
 
    summary_critical = (
        f["sum_open_fail"] or f["sum_send_fail"] or f["sum_receive_fail"] or
        f["sum_login_fail"] or f["sum_call_fail"] or f["sum_status_fail"] or
        f["sum_channel_fail"] or f["sum_load_fail"]
    )
    # Crash in summary — but not if qualified as intermittent
    if f["sum_crash"] and not intermit_combined:
        return True, "Crash signal in Summary — core function unusable."
 
    if summary_critical:
        return True, "Hard failure signal found in Summary — core function unusable."
 
    # Crash anywhere
    if f["has_crash"]:
        # Check intermittent FIRST — intermittent crash → High, not Gating
        intermit = any(t in combined for t in [
            "sometimes", "occasionally", "random", "rarely", "intermittent",
            "bazen", "zaman zaman", "ara sıra", "nadir", "sometimes crashes",
            "crashes sometimes",
        ])
        if intermit:
            return False, ""  # Let Stage 2 handle it as High
        # Unqualified or reproducible crash → Gating
        return True, "Reproducible or unqualified crash — Gating."
 
    # Freeze/stuck anywhere → Gating (app unusable)
    if f["has_freeze"]:
        # But not if it's clearly intermittent
        intermit = any(t in combined for t in [
            "sometimes", "occasionally", "bazen", "zaman zaman", "ara sıra",
        ])
        if not intermit:
            return True, "App/screen freeze or stuck — unusable state, always Gating."
 
    # Fraud / data loss
    if f["has_fraud"]:
        return True, "Fraud / financial risk detected — always Gating."
    if f["has_data_loss"]:
        return True, "Permanent data loss detected — always Gating."
 
    # High failure count even if no single pattern matched
    if f["failure_term_count"] >= 3:
        return True, "Multiple failure signals — core function likely broken."
 
    # Failure in any field but high count
    any_critical = (
        f["has_open_fail"] or f["has_send_fail"] or f["has_receive_fail"] or
        f["has_login_fail"] or f["has_call_fail"] or f["has_status_fail"] or
        f["has_channel_fail"] or f["has_load_fail"]
    )
    if any_critical and f["failure_term_count"] >= 2:
        return True, "Multiple failure signals across fields — blocking issue."
 
    return False, ""
 
 
def _stage2_is_high(f: Dict, combined: str) -> Tuple[bool, str]:
    """
    Stage 2: Is this High?
    Core business action being validated — not a failure, but feature-critical.
    """
    # Intermittent crash → High (not Gating)
    if f["has_crash"]:
        intermit = any(t in combined for t in [
            "sometimes", "occasionally", "random", "rarely", "intermittent",
            "bazen", "zaman zaman", "ara sıra", "nadir",
        ])
        if intermit:
            return True, "Intermittent crash — important but not always reproducible."
 
    # Core business actions
    has_core_action = (
        f["has_send_action"] or f["has_call_action"] or f["has_status_action"] or
        f["has_channel_action"] or f["has_reaction_action"] or
        f["has_profile_action"] or f["has_notification_action"]
    )
    if has_core_action:
        # Boost if multiple actions or important area
        area = f["feature_area"]
        if area in ("chat", "calls", "channels", "status"):
            return True, f"Core business action in high-value feature area ({area})."
        return True, "Core business action — feature-level validation."
 
    # Any failure in steps/expected (not summary) → High if not Gating
    if (f["has_send_fail"] or f["has_receive_fail"] or f["has_call_fail"]):
        return True, "Failure term in steps/expected — important feature issue."
 
    # High business action count
    if f["business_action_count"] >= 2:
        return True, "Multiple business action signals — feature-critical scenario."
 
    return False, ""
 
 
def _stage3_medium_or_low(f: Dict) -> Tuple[str, str]:
    """
    Stage 3: Medium vs Low.
    Medium: UX / navigation / display / secondary interaction.
    Low: edge case, cosmetic, rare condition, no UX impact.
 
    Key rule: if cosmetic signals dominate (no real functional UX behaviour),
    output Low. Navigation/display words that only appear as context for the
    cosmetic ("icon wrong on tab bar") should NOT promote to Medium.
    """
    has_ux = (
        f["has_search"] or f["has_filter"] or f["has_navigation"] or
        f["has_history_log"] or f["has_preview"] or f["has_emoji_ui"]
    )
    # list_display alone is too generic (cosmetic descriptions use 'shown', 'displayed')
    has_ux_strong = (
        f["has_search"] or f["has_filter"] or f["has_history_log"] or
        f["has_emoji_ui"] or f["ux_term_count"] >= 5
    )
 
    # Pure cosmetic only (typo / color / alignment / icon wrong) → Low
    # "wrong icon on tab bar" — navigation word is context, not the bug itself
    if f["has_cosmetic"] and f["cosmetic_count"] >= 1:
        # Only override to Medium if strong independent UX behaviour present
        # (search/filter/history are strong; tab/icon/navigation alone are not)
        if not has_ux_strong:
            return "Low", "Cosmetic issue (typo / alignment / color / icon). No functional impact."
 
    # Strong UX signals → Medium
    if has_ux_strong or f["ux_term_count"] >= 2:
        return "Medium", "UX / navigation / data presentation scenario."
 
    if has_ux:
        return "Medium", "Secondary UX or navigation behaviour."
 
    # Settings / profile display without cosmetic → Medium
    if f["has_settings_display"] or f["has_profile_display"]:
        if not f["has_cosmetic"]:
            return "Medium", "Settings or profile display scenario."
 
    # No signals → Medium (unknown, needs review — not Low)
    return "Medium", (
        "No strong signals. Defaulting to Medium — "
        "likely a functional scenario that needs manual review."
    )
 
 
# ═══════════════════════════════════════════════════════════════
# Scope detection
# ═══════════════════════════════════════════════════════════════
 
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
# Public API
# ═══════════════════════════════════════════════════════════════
 
# ═══════════════════════════════════════════════════════════════
# Reproduce frequency config
# ═══════════════════════════════════════════════════════════════
 
# How each frequency value interacts with the cascade:
#   always     → keeps / raises priority (crash that's always → Gating)
#   frequently → no change
#   occasionally → lower 1 level if Gating, no change otherwise
#   rarely     → lower 1 level
#   once       → lower 2 levels (max)
FREQ_OPTIONS = ["always", "frequently", "occasionally", "rarely", "once"]
 
FREQ_DROPS = {
    "always":       0,
    "frequently":   0,
    "occasionally": 1,   # Gating → High, High → Medium (not lower)
    "rarely":       1,
    "once":         2,
}
 
# Frequency labels shown in reason
FREQ_LABELS = {
    "always":       "Always reproducible",
    "frequently":   "Frequently reproducible",
    "occasionally": "Occasionally reproducible",
    "rarely":       "Rarely reproducible",
    "once":         "Reproduced once",
}
 
 
def decide_priority(
    text: str,
    actual_result: str = "",
    expected_result: str = "",
    summary: str = "",
    steps: str = "",
    reproduce_frequency: str = "always",
    device_scope: str = "",
) -> Tuple[str, bool, str, str, str, str]:
    """
    Main entry point.
 
    Params:
      summary / steps / expected_result  — field-aware inputs (preferred)
      reproduce_frequency                — one of FREQ_OPTIONS
      device_scope                       — free text e.g. "Samsung A5", "iOS 16"
 
    Returns (priority, is_scoped, scope_type, scope_detail, reason, adjusted_note)
 
    Priority adjustment rules:
      1. Reproduce frequency drops (occasionally/rarely/once → lower 1-2 levels)
         BUT: Gating with always/frequently stays Gating regardless of device scope.
      2. Device scope (specific device/OS entered manually) → lower 1 level
         Applied AFTER frequency drop.
      3. Final floor: never goes below Low.
      4. Gating with "once" still won't go below Medium (critical bugs matter).
    """
    # Normalise inputs
    if summary or steps:
        _summary  = summary
        _steps    = steps
        _expected = expected_result
    else:
        _summary  = text
        _steps    = actual_result
        _expected = expected_result
 
    combined = (_summary + " " + _steps + " " + _expected).lower()
 
    # Auto-detect device/OS scope from text if not manually provided
    auto_scoped, auto_scope_type, auto_scope_detail = detect_device_os_scope(combined)
 
    # Manual device scope overrides auto-detect
    manual_scoped = bool(device_scope.strip())
    if manual_scoped:
        is_scoped    = True
        scope_type   = "manual"
        scope_detail = device_scope.strip()
    else:
        is_scoped    = auto_scoped
        scope_type   = auto_scope_type
        scope_detail = auto_scope_detail
 
    # Normalise frequency
    freq = reproduce_frequency.lower().strip() if reproduce_frequency else "always"
    if freq not in FREQ_OPTIONS:
        freq = "always"
 
    # ── Extract features ─────────────────────────────────────
    f = extract_features(_summary, _steps, _expected)
 
    # ── Cascade ──────────────────────────────────────────────
    # Inject frequency hint into combined so crash qualifier logic works
    if freq in ("occasionally", "rarely", "once"):
        combined += " sometimes"   # makes crash intermittent in stage1
 
    is_gating, gating_reason = _stage1_is_gating(f, combined)
    if is_gating:
        base_priority = "Gating"
        reason        = REASON_MAP["Gating"] + " [" + gating_reason + "]"
    else:
        is_high, high_reason = _stage2_is_high(f, combined)
        if is_high:
            base_priority = "High"
            reason        = REASON_MAP["High"] + " [" + high_reason + "]"
        else:
            base_priority, stage3_reason = _stage3_medium_or_low(f)
            reason = REASON_MAP[base_priority] + " [" + stage3_reason + "]"
 
    # ── Feature area note ────────────────────────────────────
    area = f["feature_area"]
    reason += f" · Feature area: {area}"
 
    priority     = base_priority
    adjusted_note = ""
 
    # ── Step 1: Reproduce frequency adjustment ───────────────
    freq_drop = FREQ_DROPS.get(freq, 0)
    freq_label = FREQ_LABELS.get(freq, freq)
 
    if freq_drop > 0:
        idx = PRIORITY_ORDER.index(priority)
        new_idx = min(idx + freq_drop, len(PRIORITY_ORDER) - 1)
 
        # Special guard: Gating bugs never drop below Medium
        # (a "once" Gating crash is still at least Medium)
        if base_priority == "Gating":
            new_idx = min(new_idx, PRIORITY_ORDER.index("Medium"))
 
        if new_idx != idx:
            old_p    = priority
            priority = PRIORITY_ORDER[new_idx]
            adjusted_note += (
                f"📉 Frequency: {freq_label} — "
                f"dropped from {old_p} → {priority}. "
            )
 
    # ── Step 2: Device/OS scope adjustment ───────────────────
    if is_scoped:
        # Flagship/wide-adoption devices don't get lowered
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
                    f"dropped from {old_p} → {priority}. "
                    f"Escalate if confirmed on other devices."
                )
        else:
            adjusted_note += (
                f"📱 Device scope: {scope_detail} — "
                f"high-adoption device, priority kept at {priority}."
            )
 
    # ── Final: never below Low ───────────────────────────────
    if PRIORITY_ORDER.index(priority) > PRIORITY_ORDER.index("Low"):
        priority = "Low"
 
    return priority, is_scoped, scope_type, scope_detail, reason, adjusted_note
