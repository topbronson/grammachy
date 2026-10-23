# Pure decision logic for the AT-SPI whole-textbox helper, split out so the
# rules run under plain `python3 -m unittest` without python-gobject: CI
# covers the policy even where the live bus does not.
#
# Loaded only by `atspi_capture.py` and its tests. Nothing here may import gi.

# Roles the whole-textbox mode may read and write. Everything else —
# terminals (writing there types into a shell), documents, labels, lists —
# is refused. A combo box counts only when it carries the editable state,
# which `pick_focused` checks separately.
CHECKABLE_ROLES = frozenset(["entry", "text", "combo box"])

# Refused even when an app reports them as editable. Password fields never
# have their content read by this plugin; terminals never have text written.
NEVER_ROLES = frozenset(["password text", "terminal"])


def is_checkable_role(role_name, editable):
    """Whether an accessible with this role name and editable state may be
    whole-textbox checked. `editable` is the EDITABLE state, not a guess."""
    if not isinstance(role_name, str):
        return False
    lowered = role_name.lower()
    if lowered in NEVER_ROLES:
        return False
    if lowered not in CHECKABLE_ROLES:
        return False
    return bool(editable)


def pick_focused(focused_candidate, window_candidates):
    """The object whole-textbox mode should read.

    `focused_candidate` is the descendant the toolkit marked FOCUSED, or
    None. Some toolkits (Chromium-family among them) mark only the window
    active and never a descendant, so a single checkable descendant of the
    active window is accepted — but never a guess among several.
    Returns (candidate, None) on success or (None, reason) on refusal.
    """
    if focused_candidate is not None:
        return focused_candidate, None
    checkable = [c for c in window_candidates
                 if c is not None and is_checkable_role(c.get("role"), c.get("editable"))]
    if len(checkable) == 1:
        return checkable[0], None
    if len(checkable) == 0:
        return None, "no-editable-field"
    return None, "ambiguous-fields"


def matches_target(candidates, target):
    """Resolve the write target from live candidates under the exact-match
    rules: same role, same full text, and — when both sides carry one — the
    same pid. Zero matches is `target-gone`, more than one is
    `ambiguous-target`: a write must never land in a field we are not sure
    about, so first-match-wins is deliberately not offered.
    Returns (candidate, None) or (None, reason).
    """
    if not isinstance(target, dict):
        return None, "target-gone"
    wanted_text = target.get("all_text")
    wanted_role = target.get("role")
    if not isinstance(wanted_text, str) or wanted_text == "" or not isinstance(wanted_role, str):
        return None, "target-gone"
    hits = []
    for candidate in candidates:
        if candidate is None:
            continue
        if candidate.get("role") != wanted_role:
            continue
        if candidate.get("text") != wanted_text:
            continue
        hits.append(candidate)
    if len(hits) == 0:
        return None, "target-gone"
    if len(hits) > 1:
        return None, "ambiguous-target"
    return hits[0], None


def parse_probe_output(text):
    """The probe's stdout is one JSON object; anything else — an empty
    stream from a killed process, a traceback, a library warning mixed in
    front of the object — means no answer."""
    if not isinstance(text, str):
        return None
    stripped = text.strip()
    if not stripped.startswith("{"):
        return None
    try:
        import json
        value = json.loads(stripped)
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def probe_is_usable(probe):
    """Whether a parsed probe result can start a whole-textbox run: the bus
    answered, the field is editable, and there is something to check."""
    if not isinstance(probe, dict) or probe.get("supported") is not True:
        return False
    if probe.get("editable") is not True:
        return False
    all_text = probe.get("all_text")
    if not isinstance(all_text, str) or all_text.strip() == "":
        return False
    if probe.get("selection_empty") is not True:
        return False
    return True
