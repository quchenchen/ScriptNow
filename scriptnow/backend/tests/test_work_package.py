import json

import pytest

from scriptnow.work_package.service import (
    COVER_OUTPUT_SPECS,
    DEFAULT_COVER_OUTPUTS,
    CoverBrief,
    WorkPackageError,
    WorkPackageService,
    _download_safe_asset,
    _is_safe_https_url,
    _looks_like_image,
)


def test_packaging_agent_output_compiles_to_image_prompt_without_new_story_facts() -> None:
    payload = {
        "title": "The Electric Beloved",
        "synopsis": "A memory repairer discovers that the silicon woman he was trained to treat as property remembers a life the city erased. Their attempt to recover the truth forces them to choose between legal personhood, private love, and the safety of people who fear what she may become. As corporate hunters close in, each act of protection reveals another betrayal and tests whether goodness belongs to a species or to a choice. The journey turns their bond into evidence, weapon, and finally a demand for freedom that may cost both of them the identities they hoped to preserve.",
        "tags": ["science fiction", "silicon consciousness", "forbidden love"],
        "cover_brief": {
            "subject": "A human memory repairer facing a luminous silicon woman",
            "setting": "A rain-dark industrial city crossed by electric reflections",
            "visual_metaphor": "Their nearly touching hands split by a filament of stored memory",
            "palette": ["cobalt blue", "warm amber", "graphite black"],
            "composition": "Two figures in profile, intimate but divided, city receding behind them",
            "title_safe_area": "quiet upper third above both figures",
            "style": "restrained literary science fiction, tactile and cinematic",
            "forbidden_elements": ["weapons", "spaceships", "text", "logo"],
        },
    }

    draft = WorkPackageService.parse(json.dumps(payload))
    prompt = WorkPackageService.compile_cover_prompt(draft.cover_brief, language="en-US")

    assert "human memory repairer" in prompt
    assert "stored memory" in prompt
    assert "No text" in prompt
    assert "spaceships" in prompt
    assert "publication language is en-US" in prompt


def test_cover_prompt_is_compiled_from_structured_brief() -> None:
    brief = CoverBrief(
        subject="An exiled young woman and the wolf heir bound by a silver mark",
        setting="A winter forest at the border of two hostile packs",
        visual_metaphor="A broken moon reflected as two halves in black ice",
        palette=("moon silver", "pine black", "blood red"),
        composition="The pair separated by a diagonal scar of moonlight",
        title_safe_area="open night sky in the upper quarter",
        style="gothic paranormal romance with natural textures",
        forbidden_elements=("modern city", "guns", "text"),
    )

    prompt = WorkPackageService.compile_cover_prompt(brief)

    assert "wolf heir" in prompt
    assert "broken moon" in prompt
    assert "modern city" in prompt


def test_default_cover_outputs_target_wattpad_and_webnovel() -> None:
    assert DEFAULT_COVER_OUTPUTS == ("wattpad_hd", "webnovel")
    wattpad = COVER_OUTPUT_SPECS["wattpad_hd"]
    webnovel = COVER_OUTPUT_SPECS["webnovel"]

    assert wattpad.image2_size == "1024x1600"
    assert webnovel.image2_size == "600x800"
    assert webnovel.formats == ("jpg",)
    assert webnovel.max_bytes == 5 * 1024 * 1024


def test_user_can_adjust_agent_cover_prompt_without_losing_agent_original() -> None:
    agent_prompt = "Agent-authored visual direction"
    revised = WorkPackageService.resolve_cover_prompt(
        agent_prompt, "  Make the moon smaller and emphasize the heroine.  "
    )

    assert revised == "Make the moon smaller and emphasize the heroine."
    assert agent_prompt == "Agent-authored visual direction"


def test_packaging_parser_repairs_a_missing_json_delimiter() -> None:
    malformed = """{
      "title": "Electric Beauty",
      "synopsis": "A memory repairer discovers that the silicon woman beside him remembers the life the city erased. Their search for truth forces both of them to choose between personhood, private love, and the safety of citizens who fear artificial consciousness. Every act of protection reveals another betrayal, testing whether goodness belongs to a species or to a freely made choice. As corporate hunters close in, their bond becomes evidence, weapon, and finally a demand for freedom that may cost them both the identities they hoped to preserve.",
      "tags": ["science fiction", "silicon consciousness" "forbidden love"],
      "cover_brief": {
        "subject": "A human memory repairer facing a luminous silicon woman",
        "setting": "A rain-dark industrial city crossed by electric reflections",
        "visual_metaphor": "Their nearly touching hands divided by stored memory",
        "palette": ["cobalt blue", "warm amber"],
        "composition": "Two figures in profile with the city receding behind them",
        "title_safe_area": "quiet upper third",
        "style": "restrained literary science fiction",
        "forbidden_elements": ["text", "logo"]
      }
    }"""

    repaired = WorkPackageService.parse(malformed)

    assert repaired.title == "Electric Beauty"
    assert len(repaired.tags) == 3


@pytest.mark.parametrize(
    "value,ok",
    [
        ("https://cdn.example.com/covers/sample.png", True),
        ("http://cdn.example.com/covers/sample.png", False),
        ("https://127.0.0.1/covers/sample.png", False),
        ("https://localhost:8443/covers/sample.png", False),
        ("https://[::1]/covers/sample.png", False),
        ("not-a-url", False),
    ],
)
def test_cover_url_safety_gate(value: str, ok: bool) -> None:
    assert _is_safe_https_url(value) is ok


def test_image_magic_check_accepts_common_headers() -> None:
    assert _looks_like_image(b"\x89PNG\r\n\x1a\n", "image/png")
    assert _looks_like_image(b"\xff\xd8\xff\xe0", "image/jpeg")
    assert not _looks_like_image(b"<!DOCTYPE html>", "image/png")
    assert not _looks_like_image(b"not image data", "text/plain")


def test_safe_asset_download_rejects_private_redirect(monkeypatch) -> None:
    class FakeResponse:
        def __init__(self, status_code: int, location: str | None = None, content: bytes = b"", headers=None):
            self.status_code = status_code
            self.headers = headers or {}
            if location:
                self.headers["location"] = location
            if not self.headers and location:
                self.headers = {"Location": location}
            self.content = content

    class FakeClient:
        def __init__(self, responses):
            self.responses = iter(responses)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def get(self, url: str):
            return next(self.responses)

    monkeypatch.setattr(
        "scriptnow.work_package.service.httpx.Client",
        lambda *args, **kwargs: FakeClient(
            [
                FakeResponse(
                    302,
                    location="https://127.0.0.1/evil.png",
                ),
                FakeResponse(200, content=b"\x89PNG\r\n\x1a\n"),
            ]
        ),
    )

    with pytest.raises(WorkPackageError):
        _download_safe_asset("https://cdn.example.com/covers/sample.png", max_bytes=1024)


def test_safe_asset_download_rejects_invalid_content_length(monkeypatch) -> None:
    class FakeResponse:
        def __init__(self, content_length: str | None) -> None:
            self.status_code = 200
            self.headers = {}
            if content_length is not None:
                self.headers["content-length"] = content_length
            self.content = b"\x89PNG\r\n\x1a\n"

    class FakeClient:
        def __init__(self, response):
            self.response = response

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def get(self, url: str):
            return self.response

    monkeypatch.setattr(
        "scriptnow.work_package.service.httpx.Client",
        lambda *args, **kwargs: FakeClient(FakeResponse(content_length="not-a-number")),
    )

    with pytest.raises(WorkPackageError, match="invalid content-length"):
        _download_safe_asset("https://cdn.example.com/covers/sample.png", max_bytes=1024)


def test_safe_asset_download_limits_redirect_hops(monkeypatch) -> None:
    class FakeResponse:
        def __init__(self, status_code: int, location: str | None = None) -> None:
            self.status_code = status_code
            self.headers = {}
            if location:
                self.headers["Location"] = location
            self.content = b"\x89PNG\r\n\x1a\n"

    class FakeClient:
        def __init__(self):
            self.calls = 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def get(self, url: str):
            self.calls += 1
            return FakeResponse(302, location="https://cdn.example.com/next.png")

    fake_client = FakeClient()

    monkeypatch.setattr(
        "scriptnow.work_package.service.httpx.Client", lambda *args, **kwargs: fake_client
    )

    with pytest.raises(WorkPackageError, match="redirect exceeds maximum hops"):
        _download_safe_asset("https://cdn.example.com/covers/sample.png")
