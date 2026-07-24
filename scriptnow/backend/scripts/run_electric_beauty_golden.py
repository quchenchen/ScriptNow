"""Run the Electric Beauty long-form golden path against a live V7 API."""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[2]
GOLDEN_ROOT = ROOT / "golden" / "electric-beauty"
PROJECT_FILE = GOLDEN_ROOT / "project.json"
CHAPTER_ROOT = GOLDEN_ROOT / "chapters"
EXPORT_FILE = GOLDEN_ROOT / "electric-beauty.docx"
RESULT_FILE = GOLDEN_ROOT / "system-test-result.json"


class GoldenRun:
    def __init__(self, base_url: str) -> None:
        self.client = httpx.Client(base_url=base_url, timeout=60, trust_env=False)
        self.timings: dict[str, float] = {}
        self.project_id = ""

    def timed(self, name: str, action):
        started = perf_counter()
        result = action()
        self.timings[name] = round(perf_counter() - started, 3)
        return result

    def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        if method.upper() not in {"GET", "HEAD"}:
            headers = dict(kwargs.pop("headers", {}))
            headers["X-CSRF-Token"] = self.client.cookies["sf_csrf"]
            kwargs["headers"] = headers
        response = self.client.request(method, path, **kwargs)
        if response.is_error:
            raise RuntimeError(
                f"{method.upper()} {path} failed: {response.status_code} {response.text}"
            )
        return response

    def login(self, email: str, password: str) -> None:
        response = self.client.post("/auth/login", json={"email": email, "password": password})
        if response.is_error:
            raise RuntimeError(f"login failed: {response.status_code} {response.text}")

    def create_project(self, spec: dict[str, Any]) -> str:
        display_name = f"{spec['name']} · 全流程验收"
        projects = self.request("GET", "/projects").json()
        existing = next((item for item in projects if item["name"] == display_name), None)
        if existing:
            self.project_id = existing["id"]
            return self.project_id
        project = self.request(
            "POST",
            "/projects",
            json={
                "name": display_name,
                "medium": spec["medium"],
                "source_mode": spec["source_mode"],
                "direction": spec["direction"],
            },
        ).json()
        self.project_id = project["id"]
        return self.project_id

    def run(self, spec: dict[str, Any]) -> dict[str, Any]:
        self.timed("create_project", lambda: self.create_project(spec))
        prefix = f"/novel/projects/{self.project_id}"
        state = self.request("GET", f"{prefix}/state").json()
        adopted_documents = [item for item in state["documents"] if item["status"] == "adopted"]
        if not adopted_documents:
            cores = self.timed(
                "propose_story_cores",
                lambda: self.request(
                    "POST",
                    f"{prefix}/story-cores/propose",
                    json={
                        "idempotency_key": "electric-beauty-cores-v1",
                        "drafts": spec["story_cores"],
                    },
                ).json(),
            )
            selected = cores[int(spec["selected_core"])]
            self.request("POST", f"{prefix}/story-cores/{selected['id']}/adopt")

            blueprint = self.timed(
                "propose_blueprint",
                lambda: self.request(
                    "POST",
                    f"{prefix}/blueprints/propose",
                    json={
                        "idempotency_key": "electric-beauty-blueprint-v1",
                        "anchors": spec["blueprint"],
                    },
                ).json(),
            )
            self.request("POST", f"{prefix}/blueprints/{blueprint['id']}/adopt")

            state = self.request("GET", f"{prefix}/state").json()
            volumes = self._story_map_volumes(spec)
            structure = self.timed(
                "propose_story_map",
                lambda: self.request(
                    "POST",
                    f"{prefix}/story-map/propose",
                    json={
                        "expected_version": state["story_map"]["version"],
                        "volumes": volumes,
                        "idempotency_key": "electric-beauty-story-map-v1",
                    },
                ).json(),
            )
            self.request("POST", f"{prefix}/story-map/{structure['id']}/adopt")

        chapter_results = []
        state = self.request("GET", f"{prefix}/state").json()
        adopted_by_chapter = {
            item["chapter_id"]: item for item in state["documents"] if item["status"] == "adopted"
        }
        for chapter in spec["volumes"][0]["chapters"]:
            chapter_id = chapter["id"]
            blocks, measured_words = self._chapter_blocks(chapter_id)
            if chapter_id in adopted_by_chapter:
                candidate = adopted_by_chapter[chapter_id]
            else:
                candidate = self.timed(
                    f"write_{chapter_id}",
                    lambda chapter_id=chapter_id, blocks=blocks: self.request(
                        "POST",
                        f"{prefix}/chapters/{chapter_id}/propose",
                        json={
                            "idempotency_key": f"electric-beauty-{chapter_id}-v1",
                            "blocks": blocks,
                        },
                    ).json(),
                )
                self.request(
                    "POST",
                    f"{prefix}/chapters/{chapter_id}/revisions/{candidate['id']}/adopt",
                )
            chapter_results.append(
                {
                    "chapter_id": chapter_id,
                    "title": chapter["title"],
                    "target_words": chapter["target_words"],
                    "measured_characters": measured_words,
                    "revision_id": candidate["id"],
                }
            )

        findings = []
        for chapter in spec["volumes"][0]["chapters"]:
            finding = self.request(
                "POST",
                f"/projects/{self.project_id}/units/{chapter['id']}/review/scan",
                json={"idempotency_key": f"electric-beauty-review-{chapter['id']}-v1"},
            ).json()
            findings.append(finding)

        before_edit = self.request("GET", f"{prefix}/state").json()
        chapter_one = next(
            item
            for item in before_edit["documents"]
            if item["chapter_id"] == "chapter-01" and item["status"] == "adopted"
        )
        prose = next(block for block in chapter_one["blocks"] if block["type"] == "prose")
        excerpt = prose["text"][:16]
        edit = self.request(
            "POST",
            f"{prefix}/chapters/chapter-01/selection-edits",
            json={
                "revision_id": chapter_one["id"],
                "element_id": prose["block_id"],
                "excerpt": excerpt,
                "operation": "polish",
                "instruction": "让开场意象更具触感，但不改变事实和人物动机。",
                "idempotency_key": "electric-beauty-opening-polish-v1",
            },
        ).json()
        self.request("POST", f"{prefix}/chapters/chapter-01/revisions/{edit['id']}/adopt")

        snapshot = self.request(
            "POST",
            f"{prefix}/snapshots",
            json={"name": "十五章正文与首轮审读完成"},
        ).json()
        options = self.request("GET", f"{prefix}/exports/options").json()
        chapter_ids = [item["id"] for item in spec["volumes"][0]["chapters"]]
        manifest = self.timed(
            "export_docx",
            lambda: self.request(
                "POST",
                f"{prefix}/exports",
                json={
                    "chapter_ids": chapter_ids,
                    "form": "clean",
                    "idempotency_key": "electric-beauty-clean-export-v1",
                },
            ).json(),
        )
        artifact = self.request("GET", f"{prefix}/exports/{manifest['id']}/download").content
        EXPORT_FILE.write_bytes(artifact)

        final_state = self.request("GET", f"{prefix}/state").json()
        adopted_documents = [
            item for item in final_state["documents"] if item["status"] == "adopted"
        ]
        result = {
            "run_at": datetime.now(UTC).isoformat(),
            "project_id": self.project_id,
            "project_url": f"http://127.0.0.1:5174/projects/{self.project_id}",
            "phase": final_state["phase"],
            "story_core_candidates": len(final_state["story_cores"]),
            "blueprint_anchors": len(final_state["blueprint"]["anchors"]),
            "volumes": len(final_state["story_map"]["volumes"]),
            "chapters": len(chapter_results),
            "adopted_documents": len(adopted_documents),
            "source_characters": sum(item["measured_characters"] for item in chapter_results),
            "chapter_results": chapter_results,
            "review_findings": len(findings),
            "review_finding_ids": [item["id"] for item in findings],
            "selection_edit": {"id": edit["id"], "diff": edit["diff"]},
            "snapshot": snapshot,
            "export_options": options,
            "export": {
                **manifest,
                "path": str(EXPORT_FILE),
                "download_sha256": sha256(artifact).hexdigest(),
            },
            "timings_seconds": self.timings,
        }
        RESULT_FILE.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return result

    @staticmethod
    def _story_map_volumes(spec: dict[str, Any]) -> list[dict[str, Any]]:
        volumes = []
        all_anchor_ids = [anchor["id"] for anchor in spec["blueprint"]]
        for volume in spec["volumes"]:
            chapters = []
            for chapter in volume["chapters"]:
                chapters.append(
                    {
                        "id": chapter["id"],
                        "ordinal": chapter["ordinal"],
                        "title": chapter["title"],
                        "target_words": chapter["target_words"],
                        "point_of_view": chapter["point_of_view"],
                        "beats": [
                            {
                                "id": f"beat-{chapter['ordinal']:02d}",
                                "objective": f"{chapter['beat']}：推进“{chapter['title']}”中的人物选择。",
                                "anchor_ids": all_anchor_ids,
                            }
                        ],
                    }
                )
            volumes.append(
                {**{key: volume[key] for key in ("id", "ordinal", "title")}, "chapters": chapters}
            )
        return volumes

    @staticmethod
    def _chapter_blocks(chapter_id: str) -> tuple[list[dict[str, str]], int]:
        path = CHAPTER_ROOT / f"{int(chapter_id.split('-')[1]):02d}.md"
        markdown = path.read_text(encoding="utf-8").strip()
        parts = [part.strip() for part in re.split(r"\n\s*\n", markdown) if part.strip()]
        blocks = []
        for index, part in enumerate(parts, start=1):
            block_type = "heading" if index == 1 and part.startswith("# ") else "prose"
            text = part[2:].strip() if block_type == "heading" else part.replace("\n", " ")
            blocks.append(
                {"block_id": f"{chapter_id}-block-{index:03d}", "type": block_type, "text": text}
            )
        measured = len(re.sub(r"[\s#]", "", markdown))
        return blocks, measured


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--email", default="creator@scriptnow.local")
    parser.add_argument("--password", default="scriptnow-local-password")
    args = parser.parse_args()
    spec = json.loads(PROJECT_FILE.read_text(encoding="utf-8"))
    run = GoldenRun(args.base_url)
    run.login(args.email, args.password)
    result = run.run(spec)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
