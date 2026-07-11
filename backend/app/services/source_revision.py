"""Canonical, deterministic identities for a course's current source set."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any


SOURCE_MANIFEST_ALGORITHM = "foxsay-source-manifest-v1"


def build_source_manifest(materials: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Normalize one material revision set into the V2 canonical manifest."""
    identity = [
        {
            "material_id": str(material["material_id"]),
            "revision": int(material["material_revision"]),
            "content_hash": str(material["content_hash"]),
            "kind": str(material["material_kind"]),
        }
        for material in sorted(materials, key=lambda item: str(item["material_id"]))
    ]
    return {"algorithm": SOURCE_MANIFEST_ALGORITHM, "materials": identity}


def canonical_manifest_json(manifest: Mapping[str, Any]) -> str:
    return json.dumps(manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def build_source_revision(materials: Sequence[Mapping[str, Any]]) -> tuple[str, str]:
    """Return the source revision and its canonical JSON manifest."""
    manifest_json = canonical_manifest_json(build_source_manifest(materials))
    digest = hashlib.sha256(manifest_json.encode("utf-8")).hexdigest()
    return f"src_{digest}", manifest_json


def build_knowledge_revision(*, source_revision: str, compiler_version: str) -> str:
    """Create a deterministic D0 projection identity before a job is enqueued."""
    payload = canonical_manifest_json(
        {"compiler_version": compiler_version, "source_revision": source_revision}
    )
    return f"kn_{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"
