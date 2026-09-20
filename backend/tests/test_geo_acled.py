"""ACLED page truncation is loud: the API has no documented ordering, and a
full page silently narrows the 30-day window to whatever 500 rows came back."""

import asyncio

from backend.services.geo.ingest import acled


def _rows(n: int) -> list[dict]:
    return [
        {
            "event_id_cnty": f"E{i}", "event_date": f"2026-09-{1 + i % 19:02d}",
            "event_type": "Protests", "sub_event_type": "Peaceful protest",
            "country": "Kenya", "latitude": "-1.3", "longitude": "36.8",
            "fatalities": "0", "notes": "", "actor1": "", "actor2": "",
        }
        for i in range(n)
    ]


def _stub(monkeypatch, rows):
    async def fake(url, *, params=None, **kw):
        return {"success": True, "data": rows}

    monkeypatch.setattr(acled, "fetch_json", fake)
    monkeypatch.setattr(acled.settings, "acled_email", "a@b.c")
    monkeypatch.setattr(acled.settings, "acled_key", "k")
    monkeypatch.setattr(acled._cache, "_value", None)


def test_a_full_page_warns_with_the_window_it_kept(monkeypatch, caplog):
    _stub(monkeypatch, _rows(acled._LIMIT))
    asyncio.run(acled.fetch_acled())
    assert "full page" in caplog.text
    assert "oldest kept event_date=2026-09-01" in caplog.text
    assert "newest=2026-09-19" in caplog.text


def test_a_short_page_is_quiet(monkeypatch, caplog):
    _stub(monkeypatch, _rows(acled._LIMIT - 1))
    asyncio.run(acled.fetch_acled())
    assert "full page" not in caplog.text
