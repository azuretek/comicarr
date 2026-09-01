"""verification() must hand searcher() the candidate it is currently trying.

searcher() reads ComicName, nzbid, size, nzbtitle and friends off comicinfo[0].
When verification() passed the whole verified_matches list, every candidate was
described by candidate 0 -- so the failed-release check ran against candidate 0's
nzbid for all of them, and a single previously-failed release rejected every
alternative the provider offered.
"""

import comicarr.search as search


def _candidate(nzbid, title):
    return {
        "downloadit": True,
        "chkit": None,
        "ComicTitle": title,
        "nzbid": nzbid,
        "nzbtitle": title,
        "comyear": "2011",
        "nzbprov": "NZBGeek",
        "tmpprov": "NZBGeek (newznab)",
        "IssueID": "1001",
        "ComicID": "17993",
        "newznab": None,
        "torznab": None,
        "provider_stat": {},
        "pack": False,
        "entry": {"id": nzbid, "link": "https://example.invalid/%s" % nzbid},
    }


def _is_info():
    return {
        "nzbprov": "NZBGeek",
        "RSS": "no",
        "foundc": {"status": False, "info": None},
    }


def test_each_candidate_is_described_by_itself(monkeypatch):
    """The nzbid searcher() sees must advance with the candidate."""
    seen = []

    def fake_searcher(nzbprov, nzbname, comicinfo, link, *a, **kw):
        seen.append(comicinfo[0]["nzbid"])
        return "downloadchk-fail"  # force the loop on to the next candidate

    monkeypatch.setattr(search, "searcher", fake_searcher)
    monkeypatch.setattr(search, "nzbname_create", lambda *a, **kw: "nzbname")

    matches = [_candidate("empire-id", "Invincible 085 (digital-Empire)"),
               _candidate("minutemen-id", "Invincible 085 (Minutemen-InnerDemons)")]

    search.verification(matches, _is_info())

    assert seen == ["empire-id", "minutemen-id"], (
        "second candidate was described by candidate 0: %r" % (seen,)
    )


def test_fallback_candidate_can_still_be_taken(monkeypatch):
    """A failed first candidate must not stop the second from being sent."""

    def fake_searcher(nzbprov, nzbname, comicinfo, link, *a, **kw):
        if comicinfo[0]["nzbid"] == "empire-id":
            return "downloadchk-fail"
        return {
            "nzbid": comicinfo[0]["nzbid"],
            "nzbname": "nzbname",
            "sent_to": "NZBGet",
            "alt_nzbname": None,
            "SARC": None,
        }

    monkeypatch.setattr(search, "searcher", fake_searcher)
    monkeypatch.setattr(search, "nzbname_create", lambda *a, **kw: "nzbname")
    monkeypatch.setattr(search.updater, "nzblog", lambda *a, **kw: None)
    monkeypatch.setattr(search.updater, "foundsearch", lambda *a, **kw: None)
    monkeypatch.setattr(search, "notify_snatch", lambda *a, **kw: None)

    matches = [_candidate("empire-id", "Invincible 085 (digital-Empire)"),
               _candidate("minutemen-id", "Invincible 085 (Minutemen-InnerDemons)")]

    info = _is_info()
    info.update({"ComicName": "Invincible", "ComicYear": "2003", "IssueID": "1001",
                 "ComicID": "17993", "SARC": None, "IssueArcID": None,
                 "smode": "want", "oneoff": False, "IssueNumber": "85"})

    out = search.verification(matches, info)

    assert out["foundc"]["status"] is True
    assert out["foundc"]["info"]["nzbid"] == "minutemen-id"
