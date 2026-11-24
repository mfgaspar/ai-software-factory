"""``.clarity/questions.yml``: the questions the clarity skills raise and the answers to them.

Skills write questions; compose writes only ``answer``, ``answered_by`` and ``answered_at``.
A question is pending while its ``answer`` is null and it isn't ``obsolete``. Recording
answers is all-or-nothing, and keeps every key the skills wrote (and the file's leading
comment block; YAML can't keep the others).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from compose.runner.errors import InputError
from compose.runner.state import atomic_write

QUESTIONS_FILE = "questions.yml"
Kind = Literal["setup", "gap", "conflict", "review", "approval"]
KIND_ORDER: dict[str, int] = {"setup": 0, "gap": 1, "conflict": 1, "review": 2, "approval": 3}
APPROVAL_OPTIONS = ("approve", "reject")


class _Loader(yaml.SafeLoader):
    """SafeLoader with YAML 1.2 booleans: only true/false, so an unquoted ``No, keep it``
    or ``yes`` in a skill-written option stays the text it was meant to be."""


_Loader.yaml_implicit_resolvers = {
    first: [(tag, regexp) for tag, regexp in resolvers if tag != "tag:yaml.org,2002:bool"]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_Loader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"),
    list("tTfF"),
)


class Question(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    round: int = 1
    kind: Kind
    document: str | None = None
    question: str
    details: list[str] = Field(default_factory=list)  # supporting points, one per item
    options: list[str] = Field(default_factory=list)
    recommended: str | None = None
    free_text: bool = True
    approver: str | None = None
    answer: str | None = None
    answered_by: str | None = None
    answered_at: datetime | str | None = None
    obsolete: bool = False

    @property
    def is_pending(self) -> bool:
        return self.answer is None and not self.obsolete


def _read(path: Path) -> tuple[str, dict[str, Any]]:
    """The file's leading comment block and its parsed mapping (empty when missing)."""
    if not path.is_file():
        return "", {"questions": []}
    text = path.read_text(encoding="utf-8")
    header = []
    for line in text.splitlines(keepends=True):
        if not line.startswith("#"):
            break
        header.append(line)
    try:
        data = yaml.load(text, Loader=_Loader)  # noqa: S506 - a SafeLoader subclass
    except yaml.YAMLError as exc:
        raise InputError(f"{path}: not valid YAML: {exc}") from exc
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise InputError(f"{path}: expected a mapping with a `questions` list")
    data.setdefault("questions", [])
    if data["questions"] is None:
        data["questions"] = []
    if not isinstance(data["questions"], list):
        raise InputError(f"{path}: `questions` must be a list")
    return "".join(header), data


def _as_text(value: Any) -> Any:
    """An unquoted number in an option is still its text (``10`` → ``"10"``)."""
    return str(value) if isinstance(value, int | float) and not isinstance(value, bool) else value


_LABEL = re.compile(r"\s*\((?:recommended|recommendation)\)\s*$", re.IGNORECASE)


def _unlabel(value: Any) -> Any:
    """``"Confirm (recommended)"`` -> ``"Confirm"``; anything else unchanged."""
    if not isinstance(value, str):
        return value
    while _LABEL.search(value):
        value = _LABEL.sub("", value)
    return value


def _repair(item: Any) -> None:
    """Undo the usual slips of a hand-written entry, in place, so a re-save persists the fix.

    Numbers in ``options`` and ``recommended`` become text. An unquoted flow list such as
    ``[Yes, unittest per command, Something else]`` splits at its commas; when the
    ``recommended`` text equals consecutive items joined with ``", "``, they are joined back
    into the one option it names. A ``(recommended)`` label written into an option or into
    ``recommended`` is dropped: ``recommended`` already says which option it is, and the
    terminal marks it.
    """
    if not isinstance(item, dict):
        return
    if "recommended" in item:
        item["recommended"] = _unlabel(_as_text(item["recommended"]))
    options = item.get("options")
    if not isinstance(options, list):
        return
    options = [_unlabel(_as_text(o)) for o in options]
    recommended = item.get("recommended")
    if isinstance(recommended, str) and recommended not in options and ", " in recommended:
        for start in range(len(options)):
            for end in range(start + 2, len(options) + 1):
                parts = options[start:end]
                if all(isinstance(p, str) for p in parts) and ", ".join(parts) == recommended:
                    options[start:end] = [recommended]
                    break
            else:
                continue
            break
    item["options"] = options


def _parse(path: Path, raw: list[Any]) -> list[Question]:
    questions = []
    for index, item in enumerate(raw):
        _repair(item)
        try:
            questions.append(Question.model_validate(item))
        except ValidationError as exc:
            raise InputError(
                f"{path}: question #{index + 1} is invalid: {exc}\n"
                'Write every text value in double quotes, e.g. options: ["No, keep it", "Yes"]'
            ) from exc
    return questions


def load(path: Path) -> list[Question]:
    """Every question in ``path``, in file order (none when the file doesn't exist)."""
    _, data = _read(path)
    return _parse(path, data["questions"])


def pending(questions: Iterable[Question], *, exclude_kinds: Iterable[str] = ()) -> list[Question]:
    """Pending questions ordered by kind (setup, gap and conflict, review, approval), then
    by file order."""
    excluded = set(exclude_kinds)
    chosen = [q for q in questions if q.is_pending and q.kind not in excluded]
    return sorted(chosen, key=lambda q: KIND_ORDER[q.kind])  # stable: keeps file order


def validate_answer(q: Question, answer: str, by: str) -> list[str]:
    """The problems with answering ``q`` with ``answer`` as ``by`` (empty when it's fine)."""
    if q.obsolete:
        return [f"{q.id}: the question is obsolete"]
    if q.answer is not None:
        return [f"{q.id}: already answered"]
    if not answer.strip():
        return [f"{q.id}: the answer is empty"]
    problems = []
    if q.kind == "approval":
        if q.approver is None:
            problems.append(f"{q.id}: the approval names no approver")
        elif by != q.approver:
            problems.append(f"{q.id}: only {q.approver} can answer this approval")
        if answer not in APPROVAL_OPTIONS:
            problems.append(f"{q.id}: an approval is answered with approve or reject")
    elif not q.free_text and answer not in q.options:
        choices = ", ".join(q.options) or "(none)"
        problems.append(f"{q.id}: the answer must be one of: {choices}")
    return problems


def record(path: Path, answers: Mapping[str, str], by: str, at: datetime) -> list[Question]:
    """Record ``answers`` (question id to answer) by ``by`` at ``at``, all or nothing.

    Raises :class:`InputError` listing every problem, and then writes nothing. Returns the
    answered questions.
    """
    header, data = _read(path)
    raw: list[Any] = data["questions"]
    questions = _parse(path, raw)
    by_id = {q.id: (i, q) for i, q in enumerate(questions)}
    problems = []
    for qid, answer in answers.items():
        if qid not in by_id:
            problems.append(f"{qid}: no such question")
            continue
        problems.extend(validate_answer(by_id[qid][1], answer, by))
    if problems:
        raise InputError("invalid answers:\n" + "\n".join(f"- {p}" for p in problems))
    stamp = at.isoformat()
    answered = []
    for qid, answer in answers.items():
        index, _ = by_id[qid]
        raw[index].update(answer=answer, answered_by=by, answered_at=stamp)
        answered.append(Question.model_validate(raw[index]))
    body = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)
    atomic_write(path, header + body)
    return answered
