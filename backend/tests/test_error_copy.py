"""API error messages a user can trigger must be in Spanish.

The UI is entirely Spanish; its errors were not. Of the detail strings in
backend/api, most were English, and one managed to be both at once ("Issue no
encontrado"). A user hitting a wrong password saw "Invalid credentials" in an
otherwise Spanish app.

Operator-facing messages stay in English on purpose and are listed explicitly
below, so adding a new English string is a decision someone has to make rather
than something that happens by accident.
"""

import re
from pathlib import Path

import pytest

API_DIR = Path(__file__).resolve().parents[1] / "api"

# Never read by a user in the product: a shared-secret rejection returned to a
# cron runner, Stripe webhook validation, dev-only 409s the UI already hides,
# and configuration errors that name FINVIEW_* environment variables.
OPERATOR_ONLY = frozenset({
    "Forbidden",
    "Missing stripe-signature header",
    "Invalid payload",
    "In-process schedulers are disabled on request-scoped runtimes",
    "Telegram not configured — set FINVIEW_TELEGRAM_BOT_TOKEN and FINVIEW_TELEGRAM_CHAT_ID.",
    "Telegram delivery failed — check bot token and chat ID.",
    "FINVIEW_OPENROUTER_API_KEY not configured.",
    # Returned to Cloud Scheduler, never to a browser: /geo/cron answers 500 when
    # no user's cycle completed, so a dead pipeline shows up as a failed job
    # instead of a green one. Listed as the raw source literal, f-string and all.
    "Every geo cycle failed ({len(user_ids)} users); see logs",
})

# Function words that appear in English copy and never in Spanish copy. Nouns
# both languages share (ticker, snapshot, email, captcha) are deliberately absent.
ENGLISH_MARKERS = re.compile(
    r"\b(not|found|already|invalid|must|missing|failed|unknown|cannot|exists|"
    r"please|your|this|these|the|and|with|for|are|was|be|too|required|reached)\b",
    re.I,
)

DETAIL = re.compile(r'detail=(?:f?)(["\'])((?:\\.|(?!\1).)*)\1')


def _detail_strings():
    for path in sorted(API_DIR.glob("*.py")):
        src = path.read_text()
        for match in DETAIL.finditer(src):
            yield path.name, src[: match.start()].count("\n") + 1, match.group(2)


def test_there_are_error_strings_to_check():
    """Guards the scanner itself — a regex that matches nothing passes vacuously."""
    assert len(list(_detail_strings())) > 40


@pytest.mark.parametrize(
    "location,message",
    [(f"{name}:{line}", text) for name, line, text in _detail_strings()],
)
def test_user_facing_errors_are_in_spanish(location, message):
    if message in OPERATOR_ONLY:
        return
    leak = ENGLISH_MARKERS.search(message)
    assert not leak, (
        f"{location}: English in a user-facing error — {message!r} "
        f"(matched {leak.group(0)!r}). Translate it, or add it to OPERATOR_ONLY "
        f"if no user can reach it."
    )


def test_operator_exemptions_all_still_exist():
    """A stale exemption hides the next English string that reuses its wording."""
    present = {text for _, _, text in _detail_strings()}
    stale = OPERATOR_ONLY - present
    assert not stale, f"OPERATOR_ONLY lists strings no longer in the code: {stale}"
