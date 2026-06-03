"""Regression coverage for follow-up input after cancelling a live turn."""

from pathlib import Path


ROOT = Path(__file__).parent.parent
BOOT_JS = (ROOT / "static" / "boot.js").read_text(encoding="utf-8")
MESSAGES_JS = (ROOT / "static" / "messages.js").read_text(encoding="utf-8")
UI_JS = (ROOT / "static" / "ui.js").read_text(encoding="utf-8")


def _function_body(src: str, name: str) -> str:
    start = src.index(f"function {name}(")
    depth = 0
    opened = False
    for idx in range(src.index("{", start), len(src)):
        ch = src[idx]
        if ch == "{":
            depth += 1
            opened = True
        elif ch == "}":
            depth -= 1
            if opened and depth == 0:
                return src[start : idx + 1]
    raise AssertionError(f"could not extract function {name}")


def test_cancel_sse_settles_active_pane_and_drains_queue():
    helper = _function_body(MESSAGES_JS, "_settleCancelledStreamForOwner")

    assert "_queueDrainSid=activeSid" in helper, (
        "A server-side cancel event must identify the cancelled session before "
        "calling setBusy(false), otherwise queued follow-up messages never drain."
    )
    assert "_setActivePaneIdleIfOwner()" in helper
    assert "S.busy" in helper, (
        "Cancel finalization must be transition-aware so a later local "
        "cancelStream() cleanup cannot drain a second queued item."
    )


def test_late_cancel_refresh_cannot_clobber_new_turn_start():
    guard = _function_body(MESSAGES_JS, "_cancelRefreshStillCurrent")
    cancel_idx = MESSAGES_JS.index("source.addEventListener('cancel'")
    cancel_block = MESSAGES_JS[cancel_idx : MESSAGES_JS.index("for(const _runJournalEventName", cancel_idx)]

    assert "_sendInProgressSid===activeSid" in guard, (
        "If queue drain already started the next /api/chat/start, the old "
        "cancel-session refresh must not overwrite that optimistic turn."
    )
    assert "localStream===streamId" in guard
    assert "_cancelRefreshStillCurrent()" in cancel_block


def test_local_cancel_cleanup_clears_session_runtime_state_without_double_drain():
    helper = BOOT_JS[BOOT_JS.index("async function cancelStream") : BOOT_JS.index("async function cancelSessionStream")]

    assert "S.session.active_stream_id=null" in helper
    assert "S.session.pending_user_message=null" in helper
    assert "if(S.busy) setBusy(false)" in helper, (
        "The local Stop button is the guaranteed cleanup path when no SSE "
        "cancel event arrives, but it must not drain a second queue item if "
        "the SSE cancel handler already settled the pane."
    )


def test_queue_card_can_steer_text_items_immediately():
    helper = _function_body(UI_JS, "_canSteerQueuedItem")
    render = _function_body(UI_JS, "_renderQueueChips")

    assert "S.session&&S.session.session_id===sid" in helper
    assert "S.busy" in helper
    assert "S.activeStreamId" in helper
    assert "typeof _trySteer==='function'" in helper
    assert "!files.length" in helper, (
        "Steer-now must be hidden for queued items with files because the "
        "current steer endpoint accepts text only."
    )
    assert "queue-card-steer-btn" in render
    assert "Steer now" in render
    assert "liveQ.splice(idx,1)" in render, (
        "Steer-now must remove the original queued item before calling "
        "_trySteer; if steer falls back to interrupt+queue, it will requeue "
        "exactly once."
    )
    assert "_trySteer(steerText, true)" in render
