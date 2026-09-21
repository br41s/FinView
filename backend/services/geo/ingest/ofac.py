"""OFAC recent actions — the official sanctions designations, keyless.

GDELT was measured against a week of Treasury actions (2026-09-21) and did not
carry them: a designation only became a GDELT signal when a wire story about it
geocoded inside a region box, Russia / Cuba / Venezuela / Belarus have no box,
and the wire never names the designated entities — which is the tradable
content of a sanctions action. Five OFAC actions and three BIS orders that
week produced one GDELT sanctions signal, with actors "MUSLIM → ?".

Source: ``https://ofac.treasury.gov/recent-actions`` (a dated listing) and one
page per action at ``/recent-actions/YYYYMMDD``. There is no feed or API for
recent actions (the Sanctions List Service exposes the full SDN list, not a
dated delta), so the page is read as text and the entries are parsed from the
canonical SDN entry format, which is the same on the page, in the Federal
Register notice and in the SDN files and has not changed in decades:

    NAME (a.k.a. ...), address, City, Country; DOB ...; nationality Country;
    ... (individual) [PROGRAM] [PROGRAM-EO12345] (Linked To: ...).

Kind comes from the ``(individual)`` / ``(vessel)`` / ``(aircraft)`` marker
(anything else is an entity), programs from the bracketed tags, and country
from ``nationality X`` when present, else the first country named in the
address. Only additions become events; removals and modifications are parsed
and counted but a delisting is not a thesis this slice writes.
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser

from .base import TTLCache, fetch_text
from .types import OfacAction, OfacEntry

logger = logging.getLogger(__name__)

_LISTING_URL = "https://ofac.treasury.gov/recent-actions"
_ACTION_URL = "https://ofac.treasury.gov/recent-actions/{date}"
_CACHE_TTL = 30 * 60  # one cron cycle; the site publishes at most a few times a day
_REQUEST_TIMEOUT = 20.0
# Actions older than this are not re-read: the advisor resolves a signal at +7 d
# and would otherwise re-track the same action as new once it fell out of the
# active dedup.
_WINDOW_DAYS = 3
_MAX_ACTIONS = 5

_cache = TTLCache()

_RE_ACTION_HREF = re.compile(r'href="(?:https://ofac\.treasury\.gov)?/recent-actions/(\d{8})"')
_RE_TITLE = re.compile(r"<title>(.*?)</title>", re.S | re.I)
_RE_TAG = re.compile(r"\[([A-Z0-9][A-Z0-9-]*)\]")
_RE_KIND = re.compile(r"\((individual|vessel|aircraft)\)")
_RE_NATIONALITY = re.compile(r"nationality ([A-Z][A-Za-z,' .-]*?)(?:;|\s\(|$)")
_RE_INTRO = re.compile(
    r"^The following .{0,60}?(added to|removed from|deletions have been made|"
    r"changes have been made)",
    re.I,
)

# Country name variants as OFAC writes them → slug. Only countries a rule or a
# region box can act on need to be here; an entry in no listed country is kept
# in the counts but starts no event.
COUNTRY_SLUGS: dict[str, tuple[str, ...]] = {
    "russia": ("Russia", "Russian Federation"),
    "iran": ("Iran",),
    "china": ("China", "Hong Kong", "Macau"),
    "venezuela": ("Venezuela",),
    "cuba": ("Cuba",),
    "belarus": ("Belarus",),
    "north_korea": ("Korea, North", "North Korea", "Democratic People's Republic of Korea"),
    "syria": ("Syria",),
    "myanmar": ("Burma", "Myanmar"),
    "mexico": ("Mexico",),
    "turkey": ("Turkey", "Türkiye", "Turkiye"),
    "uae": ("United Arab Emirates",),
    "india": ("India",),
    "ukraine": ("Ukraine",),
    "iraq": ("Iraq",),
    "lebanon": ("Lebanon",),
    "yemen": ("Yemen",),
    "libya": ("Libya",),
    "sudan": ("Sudan",),
    "nigeria": ("Nigeria",),
    "eritrea": ("Eritrea",),
    "ethiopia": ("Ethiopia",),
    "nicaragua": ("Nicaragua",),
    "colombia": ("Colombia",),
    "panama": ("Panama",),
    "malaysia": ("Malaysia",),
    "singapore": ("Singapore",),
    "indonesia": ("Indonesia",),
    "taiwan": ("Taiwan",),
    "japan": ("Japan",),
    "germany": ("Germany",),
    "cyprus": ("Cyprus",),
    "switzerland": ("Switzerland",),
    "united_kingdom": ("United Kingdom",),
}
_COUNTRY_PATTERNS = [
    (slug, re.compile(r"(?<![A-Za-z])" + re.escape(name) + r"(?![A-Za-z])"))
    for slug, names in COUNTRY_SLUGS.items()
    for name in sorted(names, key=len, reverse=True)
]

_BLOCK_TAGS = {"p", "li", "div", "br", "h1", "h2", "h3", "h4", "tr", "section", "article"}


class _TextExtractor(HTMLParser):
    """HTML → lines: every block element ends a line, scripts and styles are dropped."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
        elif tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self._parts.append(data)

    def lines(self) -> list[str]:
        return [
            " ".join(line.split())
            for line in "".join(self._parts).splitlines()
            if line.strip()
        ]


def html_to_lines(html: str) -> list[str]:
    parser = _TextExtractor()
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # html.parser is lenient; anything else is a garbage payload
        logger.warning("ofac page unparseable", exc_info=True)
        return []
    return parser.lines()


def _country_of(entry_text: str) -> str | None:
    head = entry_text.split("[", 1)[0]  # the tags and "Linked To" name other places
    m = _RE_NATIONALITY.search(head)
    candidates = [m.group(1)] if m else []
    for text in (*candidates, head):
        best: tuple[int, str] | None = None
        for slug, pattern in _COUNTRY_PATTERNS:
            hit = pattern.search(text)
            if hit and (best is None or hit.start() < best[0]):
                best = (hit.start(), slug)
        if best:
            return best[1]
    return None


def parse_entry(text: str, action: str) -> OfacEntry | None:
    tags = _RE_TAG.findall(text)
    if not tags:
        return None
    name = text.split(",", 1)[0].split(" (", 1)[0].strip()
    if not name:
        return None
    m = _RE_KIND.search(text)
    return OfacEntry(
        name=name,
        kind=m.group(1) if m else "entity",
        programs=tuple(dict.fromkeys(tags)),
        country=_country_of(text),
        action=action,
    )


def _intro_action(line: str) -> str | None:
    m = _RE_INTRO.match(line)
    if not m:
        return None
    verb = m.group(1).lower()
    if verb.startswith("added"):
        return "added"
    if verb.startswith("removed") or verb.startswith("deletions"):
        return "removed"
    return "changed"


def parse_action_page(html: str, date: str, url: str) -> OfacAction:
    m = _RE_TITLE.search(html or "")
    title = " ".join(m.group(1).split()) if m else ""
    entries: list[OfacEntry] = []
    mode: str | None = None
    for line in html_to_lines(html or ""):
        intro = _intro_action(line)
        if intro is not None:
            mode = intro
            continue
        if mode in ("added", "removed"):
            entry = parse_entry(line, mode)
            if entry is not None:
                entries.append(entry)
    return OfacAction(date=date, url=url, title=title, entries=entries)


def parse_listing(html: str, today: datetime | None = None) -> list[str]:
    """Action dates (YYYYMMDD) on the listing inside the window, newest first."""
    now = today or datetime.now(timezone.utc)
    floor = (now - timedelta(days=_WINDOW_DAYS)).strftime("%Y%m%d")
    dates = sorted({d for d in _RE_ACTION_HREF.findall(html or "") if d >= floor}, reverse=True)
    return dates[:_MAX_ACTIONS]


async def fetch_ofac() -> list[OfacAction]:
    cached = _cache.get(_CACHE_TTL)
    if cached is not None:
        return cached

    listing = await fetch_text(_LISTING_URL, timeout=_REQUEST_TIMEOUT)
    if not listing:
        logger.warning("ofac listing unavailable")
        return _cache.stale or []

    actions: list[OfacAction] = []
    for date in parse_listing(listing):
        url = _ACTION_URL.format(date=date)
        page = await fetch_text(url, timeout=_REQUEST_TIMEOUT)
        if not page:
            continue
        action = parse_action_page(page, date, url)
        logger.info(
            "ofac %s: %d entries (%d added) — %s", date, len(action.entries),
            sum(1 for e in action.entries if e.action == "added"), action.title[:80],
        )
        actions.append(action)

    _cache.set(actions)
    return actions
