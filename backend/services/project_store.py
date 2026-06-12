from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from schemas import ProjectSummary, SessionState


class ProjectStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, session: SessionState, name: str | None = None) -> ProjectSummary:
        project_id = uuid4().hex
        project_name = name or session.name or f"project-{project_id[:8]}"
        folder = self.root / project_id
        folder.mkdir(parents=True, exist_ok=True)
        payload = session.model_dump(mode="json")
        (folder / "session.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        summary = ProjectSummary(
            id=project_id,
            name=project_name,
            session_id=session.id,
            datasets_total=len(session.datasets),
            artifacts_total=len(session.artifacts),
            uri=str(folder),
        )
        (folder / "project.json").write_text(
            summary.model_dump_json(indent=2), encoding="utf-8"
        )
        return summary

    def list(self) -> list[ProjectSummary]:
        out: list[ProjectSummary] = []
        for path in self.root.glob("*/project.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                out.append(ProjectSummary.model_validate(data))
            except Exception:
                continue
        return sorted(out, key=lambda x: x.saved_at, reverse=True)

    def load(self, project_id: str) -> SessionState:
        path = self.root / project_id / "session.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        return SessionState.model_validate(data)

