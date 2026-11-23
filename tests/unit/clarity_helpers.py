"""Fake clarity skills for the fake engine: they write ``.clarity/`` files like the real ones.

``/clarity draft`` writes a PRD and a gap question, ``/clarity apply`` raises a review
question until one is answered, ``compose-constitution`` writes the constitution and
``clarity-validate`` passes when nothing is pending.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import yaml

from compose.clarity import constitution, fingerprint, verdict
from compose.engines.base import EngineOptions, EngineTask
from compose.engines.fake import Script, edit
from compose.repos import git

QFILE = ".clarity/questions.yml"
GAP = {"id": "Q-001", "kind": "gap", "question": "Which roles?", "recommended": "3"}
APPROVAL = {
    "id": "Q-009",
    "kind": "approval",
    "question": "Approve the PRD?",
    "options": ["approve", "reject"],
    "free_text": False,
    "approver": "someone-else",
}
ScriptFor = Callable[[EngineTask, Path, EngineOptions], Script]


def _load(cwd: Path) -> list[dict[str, object]]:
    path = cwd / QFILE
    if not path.is_file():
        return []
    return list((yaml.safe_load(path.read_text()) or {}).get("questions") or [])


def _dump(items: list[dict[str, object]]) -> str:
    return yaml.safe_dump({"questions": items}, sort_keys=False)


def skills(
    *, drafted: list[dict[str, object]] | None = None, always_ask: bool = False
) -> ScriptFor:
    """Plausible clarity skills. ``always_ask``: apply raises a new gap every round."""
    first = [GAP] if drafted is None else drafted

    def script(task: EngineTask, cwd: Path, options: EngineOptions) -> Script:
        args = task.args or ""
        if task.text == "clarity" and args.endswith("draft"):
            acts = edit(".clarity/product/prd.md", f"# PRD\nFrom: {args}\n")
            return Script([*acts, *edit(QFILE, _dump(_load(cwd) or list(first)))])
        if task.text == "clarity" and args == "apply":
            items = _load(cwd)
            if always_ask:
                n = len(items) + 1
                items.append({"id": f"Q-{n:03}", "kind": "gap", "question": f"More {n}?"})
            elif not any(q["kind"] == "review" for q in items):
                items.append({"id": "Q-002", "kind": "review", "question": "Confirm?"})
            notes = "".join(f"- {q['id']}: {q.get('answer')}\n" for q in items)
            acts = edit(".clarity/product/prd.md", f"# PRD\n{notes}")
            return Script([*acts, *edit(QFILE, _dump(items))])
        if task.text == "compose-constitution":
            return Script(edit(constitution.CONSTITUTION_FILE, "# Constitution\n"))
        if task.text == "clarity-validate":
            pending = [q for q in _load(cwd) if q.get("answer") is None]
            last = f"CLARITY: FAIL ({len(pending)} incomplete)" if pending else "CLARITY: PASS"
            return Script(final_text=f"Checked.\n{last}")
        return Script()

    return script


def foundation(root: Path) -> str:
    """Commit a passing clarity foundation on ``root``'s current branch: a document, the
    constitution stamped with its fingerprint, and a PASS verdict. Returns the fingerprint."""
    (root / ".clarity/product").mkdir(parents=True, exist_ok=True)
    (root / ".clarity/product/prd.md").write_text("# PRD\n")
    git.git(root, "add", "-A")
    git.git(root, "commit", "-q", "-m", "clarity")
    fp = fingerprint.of_ref(root, "HEAD")
    path = root / constitution.CONSTITUTION_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{constitution.marker(fp)}\n# Constitution\n")
    verdict.write(root, verdict.Verdict("PASS", 0), fp, "run-x")
    git.git(root, "add", "-A")
    git.git(root, "commit", "-q", "-m", "validated")
    return fp
