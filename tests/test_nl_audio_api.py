"""Tests for Dutch audio assembly and the Groq-backed generators."""

import json
import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from pydub import AudioSegment

from scripts.nl import nl_tts, seo, shorts, topics as nl_topics
from scripts.nl import script_generator as sg
from scripts.nl.variation import build_variant


def _silence(path: Path, ms: int) -> Path:
    AudioSegment.silent(duration=ms).export(str(path), format="mp3")
    return path


class _Response:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")

    def json(self):
        return self._payload


def _groq_response(content: dict | str):
    body = content if isinstance(content, str) else json.dumps(content)
    return _Response({"choices": [{"message": {"content": body}}]})


# ── audio ──────────────────────────────────────────────

def test_duration_of_reads_real_audio(tmp_path):
    assert nl_tts.duration_of(_silence(tmp_path / "a.mp3", 1500)) == pytest.approx(1.5, abs=0.1)


def test_combine_inserts_the_base_pause_between_sections(tmp_path):
    files = [_silence(tmp_path / f"{i}.mp3", 1000) for i in range(2)]

    out = nl_tts.combine(files, tmp_path / "vol.mp3", pause_ms=400,
                         sections=[{"narration": "Gewoon einde."}, {"narration": "x"}])

    assert nl_tts.duration_of(out) == pytest.approx(2.4, abs=0.15)


def test_combine_holds_longer_after_a_cliffhanger(tmp_path):
    files = [_silence(tmp_path / f"c{i}.mp3", 1000) for i in range(2)]

    plain = nl_tts.combine(files, tmp_path / "plain.mp3", pause_ms=400,
                           sections=[{"narration": "Gewoon einde."}, {"narration": "x"}])
    hooked = nl_tts.combine(files, tmp_path / "hooked.mp3", pause_ms=400,
                            sections=[{"narration": "En toen?"}, {"narration": "x"}])

    assert nl_tts.duration_of(hooked) > nl_tts.duration_of(plain)


def test_combine_adds_no_trailing_pause(tmp_path):
    one = [_silence(tmp_path / "solo.mp3", 1000)]

    out = nl_tts.combine(one, tmp_path / "single.mp3", pause_ms=900)

    assert nl_tts.duration_of(out) == pytest.approx(1.0, abs=0.15)


def test_synthesize_sections_skips_empty_narration(tmp_path, monkeypatch):
    monkeypatch.setattr(nl_tts, "synthesize",
                        lambda text, path, voice: Path(path).write_bytes(b"x") or Path(path))
    sections = [{"narration": "Wel."}, {"narration": "   "}, {"narration": "Ook."}]

    paths = nl_tts.synthesize_sections(sections, "slug", build_variant("x").voice, tmp_path)

    assert len(paths) == 2


# ── script generation ──────────────────────────────────

def test_generate_script_returns_a_validated_script(monkeypatch):
    monkeypatch.setattr(sg, "research_topic_nl", lambda topic: "FEITEN")
    monkeypatch.setattr(sg.requests, "post",
                        lambda *a, **kw: _groq_response({
                            "title": "T", "description": "D",
                            "tags": ["de", "deltawerken"], "hook": "H",
                            "eigen_invalshoek": "Een stelling.",
                            "sections": [{"narration": "In 1953 brak de dijk.",
                                          "visual_keywords": ["storm surge"]}],
                        }))

    script = sg.generate_script_nl("Deltawerken", build_variant("Deltawerken"))

    assert script["tags"] == ["deltawerken"]  # Dutch stopword dropped
    assert script["eigen_invalshoek"] == "Een stelling."


def test_generate_script_retries_then_gives_up_on_sustained_rate_limits(monkeypatch):
    monkeypatch.setattr(sg, "research_topic_nl", lambda topic: "")
    monkeypatch.setattr(sg.time, "sleep", lambda s: None)
    monkeypatch.setattr(sg.requests, "post", lambda *a, **kw: _Response({}, status=429))

    with pytest.raises(RuntimeError, match="rate limit"):
        sg.generate_script_nl("Deltawerken", build_variant("x"))


def test_generate_script_recovers_when_a_retry_succeeds(monkeypatch):
    monkeypatch.setattr(sg, "research_topic_nl", lambda topic: "")
    monkeypatch.setattr(sg.time, "sleep", lambda s: None)
    attempts = {"n": 0}

    def post(*a, **kw):
        attempts["n"] += 1
        if attempts["n"] == 1:
            return _Response({}, status=429)
        return _groq_response({"title": "T", "tags": [], "hook": "",
                               "description": "", "sections": [],
                               "eigen_invalshoek": "Stelling."})

    monkeypatch.setattr(sg.requests, "post", post)

    assert sg.generate_script_nl("x", build_variant("x"))["title"] == "T"


# ── shorts ─────────────────────────────────────────────

def test_short_hook_extraction_parses_the_model_json(monkeypatch):
    monkeypatch.setattr(shorts.requests, "post",
                        lambda *a, **kw: _groq_response({
                            "narration": "Kort fragment.",
                            "visual_keywords": ["storm surge barrier"],
                            "hook_text": "De rekening",
                        }))

    hook = shorts.extract_short_hook_nl({"hook": "H", "sections": []},
                                        build_variant("x"))

    assert hook["hook_text"] == "De rekening"


def test_short_hook_extraction_propagates_api_failure(monkeypatch):
    monkeypatch.setattr(shorts.requests, "post",
                        lambda *a, **kw: _Response({}, status=500))

    with pytest.raises(requests.HTTPError):
        shorts.extract_short_hook_nl({"hook": "H", "sections": []},
                                     build_variant("x"))


# ── seo ────────────────────────────────────────────────

def test_seo_optimization_returns_a_new_dict(monkeypatch):
    monkeypatch.setattr(seo, "research_terms_nl",
                        lambda topic: {"direct": [], "related": [], "top": []})
    monkeypatch.setattr(seo, "optimize_title_nl",
                        lambda topic, current, terms: ["Betere titel", "Alt"])
    original = {"title": "Oude titel", "description": "D", "tags": ["deltawerken"]}
    snapshot = dict(original)

    optimized = seo.optimize_script_seo_nl(original)

    assert original == snapshot
    assert optimized["title"] == "Betere titel"
    assert optimized["title_alternatives"] == ["Alt"]


def test_seo_keeps_the_original_title_when_groq_fails(monkeypatch):
    monkeypatch.setattr(seo, "research_terms_nl",
                        lambda topic: {"direct": [], "related": [], "top": []})

    def boom(*a, **kw):
        raise requests.RequestException("groq down")

    monkeypatch.setattr(seo, "optimize_title_nl", boom)

    optimized = seo.optimize_script_seo_nl({"title": "Oude titel", "tags": []})

    assert optimized["title"] == "Oude titel"
    assert seo.DISCLOSURE_NL in optimized["description"]


def test_title_candidates_drop_numbering_and_overlong_lines(monkeypatch):
    monkeypatch.setattr(seo.requests, "post", lambda *a, **kw: _groq_response(
        "1. Hoe de Deltawerken werken\n2. " + "x" * 200 + "\n3. De rekening van 1953"
    ))

    titles = seo.optimize_title_nl("deltawerken", "oud", {"top": []})

    assert titles == ["Hoe de Deltawerken werken", "De rekening van 1953"]


def test_research_terms_skips_prefixes_too_short_to_be_topical(monkeypatch):
    seen: list = []

    def suggest(query):
        seen.append(query)
        return []

    monkeypatch.setattr(seo, "youtube_suggest_nl", suggest)
    monkeypatch.setattr(seo.time, "sleep", lambda s: None)

    seo.research_terms_nl("hoe werkt een polder")

    assert not [q for q in seen if q in ("hoe", "hoe werkt")]


# ── topics I/O ─────────────────────────────────────────

def test_nos_headlines_skips_the_feed_title(monkeypatch):
    feed = ("<rss><channel><title>NOS Nieuws</title>"
            "<item><title>Dijken houden het bij zware storm vannacht</title></item>"
            "</channel></rss>")
    monkeypatch.setattr(nl_topics.requests, "get",
                        lambda *a, **kw: _Response_text(feed))

    assert nl_topics.nos_headlines() == [
        "Dijken houden het bij zware storm vannacht"]


def test_nos_headlines_degrades_on_network_failure(monkeypatch):
    def boom(*a, **kw):
        raise requests.RequestException("nos down")

    monkeypatch.setattr(nl_topics.requests, "get", boom)

    assert nl_topics.nos_headlines() == []


def test_save_topics_writes_readable_dutch(tmp_path):
    found = [nl_topics.Topic("hoe werkt een sluis", 2, True, "autocomplete")]

    path = nl_topics.save_topics(found, tmp_path / "out.json")

    payload = json.loads(path.read_text())
    assert payload[0]["topic"] == "hoe werkt een sluis"
    assert payload[0]["evergreen"] is True


class _Response_text:
    """RSS comes back as text, not JSON."""

    def __init__(self, text):
        self.text = text
        self.status_code = 200

    def raise_for_status(self):
        pass
