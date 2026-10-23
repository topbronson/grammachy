#!/usr/bin/env python3
"""Read or write the focused editable field through AT-SPI, no keystrokes.

  atspi_capture.py probe                 -> one JSON object on stdout
  atspi_capture.py write '<identity>'    -> corrected full text on stdin,
                                            one JSON object on stdout

`probe` answers for the keyboard-focused editable field (or, where a toolkit
marks only the window active, its single editable descendant). `write`
re-resolves the field the probe recorded — same role, same full text,
never a guess among several — and replaces its content. A sentinel line
names every invocation on stderr so the shell journal can show that the
helper ran at all; stdout carries only the JSON answer.

The QML side wraps this in `timeout`; a second, shorter alarm fires here so
a wedged app answers `unsupported` instead of hanging the bus round trip.
"""

import json
import sys
from typing import NoReturn

from atspi_lib import (matches_target, parse_probe_output, pick_focused,
                       is_checkable_role)

# A D-Bus round trip into a wedged app can block forever; alarm before
# `timeout` does, so the answer is a clean unsupported rather than nothing.
TIMEOUT_SECONDS = 4

MAX_VISITS = 20000
MAX_DEPTH = 30


def _fail(reason) -> NoReturn:
    print("grammachy atspi: unsupported (%s)" % reason, file=sys.stderr)
    print(json.dumps({"supported": False, "reason": reason}))
    sys.exit(0)


def _alarm_fired(_signum, _frame):
    _fail("timeout")


def _text_of(obj):
    """The widget's full text through the Text interface, or None.

    The interface-qualified calls are mandatory: the instance methods with
    the same names are different, deprecated accessors (`get_text` on the
    Accessible takes one argument and is not the Text call)."""
    try:
        count = Atspi.Text.get_character_count(obj)
    except Exception:
        return None
    if count <= 0:
        return ""
    try:
        return Atspi.Text.get_text(obj, 0, count)
    except Exception:
        return None


def _selection_is_empty(obj):
    try:
        n = Atspi.Text.get_n_selections(obj)
    except Exception:
        return False
    if n == 0:
        return True
    try:
        for i in range(n):
            _start, end = Atspi.Text.get_selection(obj, i)
            if end > _start:
                return False
    except Exception:
        return False
    return True


def _candidate(obj):
    """A plain-dict snapshot of one accessible, the currency the pure
    matching rules work in."""
    try:
        role = obj.get_role_name()
        editable = obj.get_state_set().contains(Atspi.StateType.EDITABLE)
        pid = obj.get_process_id()
        # Chromium exposes web text fields as read-only: they carry Text
        # but no EditableText, so a write there can never be proven. The
        # flag rides through probe/identity so the pure rules can refuse
        # the write up front instead of attempting it. Interface names
        # come back short ("EditableText") from gi but may arrive fully
        # qualified from other bindings, so match the suffix.
        try:
            editable_text = any(str(n).endswith("EditableText")
                                for n in obj.get_interfaces())
        except Exception:
            editable_text = True  # unknown: attempt and let readback decide
    except Exception:
        return None
    if role is None:
        return None
    return {"obj": obj, "role": role, "editable": bool(editable),
            "editable_text": bool(editable_text), "pid": pid}


def _walk(root, visit, max_visits=MAX_VISITS):
    """Depth-first walk with a hard visit cap; returns False if truncated."""
    stack = [(root, 0)]
    visits = 0
    while stack:
        node, depth = stack.pop()
        visits += 1
        if visits > max_visits:
            return False
        stop = visit(node, depth)
        if stop:
            return True
        if depth >= MAX_DEPTH:
            continue
        try:
            n = node.get_child_count()
        except Exception:
            n = 0
        for i in reversed(range(n)):
            try:
                child = node.get_child_at_index(i)
            except Exception:
                child = None
            if child is not None:
                stack.append((child, depth + 1))
    return True


def _find_focused(window):
    """The descendant the toolkit itself marked FOCUSED, if any."""
    found = []

    def visit(node, _depth):
        try:
            if node.get_state_set().contains(Atspi.StateType.FOCUSED):
                found.append(node)
                return True
        except Exception:
            pass
        return False

    _walk(window, visit)
    return found[0] if found else None


def _editable_descendants(window):
    out = []

    def visit(node, _depth):
        cand = _candidate(node)
        if cand is not None and is_checkable_role(cand["role"], cand["editable"]):
            out.append(cand)
        return False

    _walk(window, visit)
    return out


def _windows_for_pid(pid):
    """Every window the bus reports for one client pid, preferring the ones
    the toolkit marks ACTIVE. Resolving by the compositor's focused pid is
    what keeps the shell's own bars (always on the bus, sometimes marked
    active) from posing as the target."""
    out = []
    try:
        desktop = Atspi.get_desktop(0)
        for i in range(desktop.get_child_count()):
            try:
                app = desktop.get_child_at_index(i)
                if app is None or app.get_process_id() != pid:
                    continue
                n = app.get_child_count()
            except Exception:
                continue
            for w in range(n):
                try:
                    win = app.get_child_at_index(w)
                    if win is not None:
                        out.append(win)
                except Exception:
                    continue
    except Exception:
        return []
    active = []
    for win in out:
        try:
            if win.get_state_set().contains(Atspi.StateType.ACTIVE):
                active.append(win)
        except Exception:
            continue
    return active if active else out


def _active_windows():
    """Windows the bus reports ACTIVE, outside this helper's own pid. The
    fallback when the caller could not name a focused pid."""
    my_pid = None
    try:
        import os
        my_pid = os.getpid()
    except Exception:
        pass
    windows = []
    try:
        desktop = Atspi.get_desktop(0)
        apps = desktop.get_child_count()
    except Exception:
        return windows
    for i in range(apps):
        try:
            app = desktop.get_child_at_index(i)
            if app is None:
                continue
            app_pid = app.get_process_id()
            if my_pid is not None and app_pid == my_pid:
                continue
            n = app.get_child_count()
        except Exception:
            continue
        for w in range(n):
            try:
                win = app.get_child_at_index(w)
                if win is None:
                    continue
                if win.get_state_set().contains(Atspi.StateType.ACTIVE):
                    windows.append(win)
            except Exception:
                continue
    return windows


def _resolve_windows(pid):
    if pid is not None:
        windows = _windows_for_pid(pid)
        if not windows:
            _fail("pid-not-on-bus")
        return windows
    windows = _active_windows()
    if not windows:
        _fail("no-active-window")
    # A summon can land while two windows race for active (a click on one,
    # the keyboard still on the other). Refuse rather than read the wrong
    # window's field.
    if len(windows) > 1:
        _fail("ambiguous-windows")
    return windows


def do_probe(pid=None):
    windows = _resolve_windows(pid)
    window = windows[0]
    focused = _find_focused(window)
    focused_cand = None
    if focused is not None:
        focused_cand = _candidate(focused)
        if focused_cand is not None and is_checkable_role(focused_cand["role"],
                                                         focused_cand["editable"]):
            pass
        else:
            # The toolkit marked something non-editable as focused — a
            # dialog's OK button among them. The caret-able field is still
            # the intended target: take it when exactly one exists.
            focused = None
    if focused is None:
        # Either nothing carries FOCUSED or a button does: accept the window
        # only when exactly one field could have been meant.
        editable = _editable_descendants(window)
        focused_cand, reason = pick_focused(None, editable)
        if focused_cand is None:
            _fail(reason)

    obj = focused_cand["obj"]
    all_text = _text_of(obj)
    if all_text is None:
        _fail("text-interface-unavailable")
    if not _selection_is_empty(obj):
        # A real selection exists but never reached the primary clipboard
        # path; that run belongs to the normal capture, not to this helper.
        _fail("selection-not-empty")

    try:
        window_name = window.get_name() or ""
    except Exception:
        window_name = ""
    print("grammachy atspi: probe ok role=%s chars=%d" % (focused_cand["role"], len(all_text)),
          file=sys.stderr)
    print(json.dumps({
        "supported": True,
        "pid": focused_cand["pid"],
        "window": window_name,
        "role": focused_cand["role"],
        "editable": True,
        "editable_text": bool(focused_cand.get("editable_text", True)),
        "selection_empty": True,
        "all_text": all_text
    }))
    sys.exit(0)


def _write_back(obj, new_text):
    """Replace the widget's content, preferring the whole-replace call and
    falling back to delete + insert for apps that do not implement it."""
    old_len = len(_text_of(obj) or "")
    try:
        if Atspi.EditableText.set_text_contents(obj, new_text):
            return True
    except Exception:
        pass
    try:
        Atspi.EditableText.delete_text(obj, 0, old_len)
        Atspi.EditableText.insert_text(obj, 0, new_text, len(new_text))
        return True
    except Exception:
        return False


def do_write(identity_json):
    target = parse_probe_output(identity_json)
    if target is None:
        _fail("bad-identity")
    new_text = sys.stdin.read()
    if new_text == "":
        _fail("empty-write")

    # The card holds focus by accept time, so resolve by the recorded pid
    # rather than by anything the bus calls active.
    pid = target.get("pid")
    candidates = []
    for win in _windows_for_pid(pid if isinstance(pid, int) else -1):
        def visit(node, _depth):
            cand = _candidate(node)
            if cand is not None:
                cand["text"] = _text_of(node)
                candidates.append(cand)
            return False

        _walk(win, visit)

    hit, reason = matches_target(candidates, target)
    if hit is None:
        _fail(reason)
    if not _write_back(hit["obj"], new_text):
        _fail("write-refused")
    # Success is an observation, not an assumption: read the widget again
    # and only claim the write when the text actually changed.
    if _text_of(hit["obj"]) != new_text:
        _fail("write-unverified")
    print("grammachy atspi: write ok chars=%d" % len(new_text), file=sys.stderr)
    print(json.dumps({"written": True, "verified": True, "len": len(new_text)}))
    sys.exit(0)


def main():
    import signal

    global Atspi
    signal.signal(signal.SIGALRM, _alarm_fired)
    # The alarm bites between AT-SPI calls, which are synchronous D-Bus
    # round trips — where a wedged app hangs us anyway. `timeout` upstream
    # is the outer bound; this is the polite inner one.
    signal.alarm(TIMEOUT_SECONDS)

    try:
        import gi  # type: ignore[import-not-found]
        gi.require_version("Atspi", "2.0")
        from gi.repository import Atspi  # type: ignore[import-not-found] # noqa: F401 (binds the module global)
    except Exception:
        _fail("no-gi")

    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "probe":
        pid = None
        if len(sys.argv) > 2 and sys.argv[2].isdigit():
            pid = int(sys.argv[2])
        do_probe(pid)
    elif mode == "write":
        do_write(sys.argv[2] if len(sys.argv) > 2 else "")
    _fail("bad-mode")


if __name__ == "__main__":
    main()
