"""Landing-zone bookkeeping for the EHR extract volume.

Layout under /Volumes/<catalog>/ehr_raw/ehr_landing:

    <entity>/extract_date=YYYY-MM-DD/part-*.json   extract records (JSON lines)
    _manifests/run_<run_id>.json                   dates landed by one run, with row counts

An extract date counts as landed only when a manifest lists it. Date folders that
exist without a manifest are leftovers of an interrupted run and are removed before
re-landing, so reruns converge on the same files.
"""

from __future__ import annotations

import io
import json
from datetime import date, datetime, timezone

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound

MANIFEST_DIR = "_manifests"
_PREFIX = "extract_date="


class VolumeLanding:
    def __init__(self, ws: WorkspaceClient, root: str) -> None:
        self.ws = ws
        self.root = root.rstrip("/")

    def manifests(self) -> list[dict]:
        found = []
        for entry in self._list(f"{self.root}/{MANIFEST_DIR}"):
            if entry.is_directory or not entry.name.endswith(".json"):
                continue
            with self.ws.files.download(entry.path).contents as fh:
                found.append(json.load(fh))
        return found

    def remove_unmanifested(self, entities: tuple[str, ...], landed: set[date]) -> list[str]:
        """Delete date folders not covered by any manifest; return what was removed."""
        removed = []
        for entity in entities:
            for entry in self._list(f"{self.root}/{entity}"):
                if not (entry.is_directory and entry.name.startswith(_PREFIX)):
                    continue
                if date.fromisoformat(entry.name[len(_PREFIX):]) not in landed:
                    self._delete_tree(entry.path)
                    removed.append(entry.path)
        return removed

    def write_manifest(self, run_id: str, dates: list[date], row_counts: dict, metadata: dict) -> str:
        path = f"{self.root}/{MANIFEST_DIR}/run_{run_id}.json"
        body = {
            "run_id": run_id,
            "written_at": datetime.now(timezone.utc).isoformat(),
            "extract_dates": [d.isoformat() for d in sorted(dates)],
            "row_counts": row_counts,
            **metadata,
        }
        self.ws.files.create_directory(f"{self.root}/{MANIFEST_DIR}")
        self.ws.files.upload(path, io.BytesIO(json.dumps(body, indent=2).encode()), overwrite=True)
        return path

    def _list(self, directory: str):
        try:
            return list(self.ws.files.list_directory_contents(directory))
        except NotFound:
            return []

    def _delete_tree(self, directory: str) -> None:
        for entry in self._list(directory):
            if entry.is_directory:
                self._delete_tree(entry.path)
            else:
                self.ws.files.delete(entry.path)
        self.ws.files.delete_directory(directory)


def landed_dates(manifests: list[dict]) -> set[date]:
    return {date.fromisoformat(d) for m in manifests for d in m["extract_dates"]}


def assert_single_generator_version(manifests: list[dict], current: str) -> None:
    """Refuse to mix extract schemas from different generator versions in one volume."""
    other = sorted({str(m.get("generator_version")) for m in manifests} - {current})
    if other:
        raise RuntimeError(
            f"Landing zone holds extracts from generator version(s) {other}; this run is "
            f"version {current}. Clear the landing volume (and reset downstream pipeline "
            "state) before re-landing with the new version."
        )
