""".clarity/questions.yml: loading, pending order, answer validation and recording."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from compose.clarity import questions
from compose.engines.claude.install import ASSETS
from compose.runner.errors import InputError

AT = datetime(2026, 11, 23, 10, 0, tzinfo=UTC)


def _q(qid: str, kind: str = "gap", **fields: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": qid,
        "round": 1,
        "kind": kind,
        "document": None if kind == "setup" else "product/prd.md",
        "question": f"question {qid}?",
        "options": [],
        "recommended": None,
        "free_text": True,
        "approver": None,
        "answer": None,
        "answered_by": None,
        "answered_at": None,
    }
    data.update(fields)
    return data


def _write(tmp_path: Path, *items: dict[str, Any], header: str = "") -> Path:
    path = tmp_path / "questions.yml"
    path.write_text(header + yaml.safe_dump({"questions": list(items)}, sort_keys=False))
    return path


def _approval(qid: str = "Q-9") -> dict[str, Any]:
    return _q(qid, "approval", options=["approve", "reject"], free_text=False, approver="ana")


def test_template_is_an_empty_list() -> None:
    path = ASSETS / "templates" / "clarity" / "questions.yml"
    assert questions.load(path) == []
    assert path.read_text().startswith("#")


def test_missing_file_has_no_questions(tmp_path: Path) -> None:
    assert questions.load(tmp_path / "questions.yml") == []


def test_malformed_file_is_an_input_error(tmp_path: Path) -> None:
    path = tmp_path / "questions.yml"
    path.write_text("questions: {not: a list}\n")
    with pytest.raises(InputError):
        questions.load(path)
    path.write_text("questions:\n  - id: Q-1\n")  # no kind, no question
    with pytest.raises(InputError):
        questions.load(path)


def test_pending_orders_by_kind_then_file_order(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        _approval("Q-1"),
        _q("Q-2", "review"),
        _q("Q-3", "conflict"),
        _q("Q-4", "setup"),
        _q("Q-5", "gap"),
        _q("Q-6", "setup"),
        _q("Q-7", "gap", answer="yes", answered_by="ana", answered_at="2026-11-01T00:00:00"),
    )
    loaded = questions.load(path)
    assert [q.id for q in questions.pending(loaded)] == ["Q-4", "Q-6", "Q-3", "Q-5", "Q-2", "Q-1"]
    no_approvals = questions.pending(loaded, exclude_kinds=("approval",))
    assert [q.id for q in no_approvals] == ["Q-4", "Q-6", "Q-3", "Q-5", "Q-2"]


def test_obsolete_questions_are_not_pending(tmp_path: Path) -> None:
    path = _write(tmp_path, _q("Q-1", obsolete=True), _q("Q-2"))
    loaded = questions.load(path)
    assert loaded[0].obsolete and not loaded[0].is_pending
    assert [q.id for q in questions.pending(loaded)] == ["Q-2"]


def _question(**fields: Any) -> questions.Question:
    return questions.Question.model_validate(_q("Q-1", **fields))


def test_free_text_accepts_any_non_empty_answer() -> None:
    q = _question(options=["a", "b"], free_text=True)
    assert questions.validate_answer(q, "something else", "bo") == []
    assert questions.validate_answer(q, "a", "bo") == []
    assert questions.validate_answer(q, "  ", "bo") != []


def test_options_only_accepts_an_option() -> None:
    q = _question(options=["3 roles (PRD)", "2 roles (code)"], free_text=False)
    assert questions.validate_answer(q, "2 roles (code)", "bo") == []
    assert "must be one of" in questions.validate_answer(q, "4 roles", "bo")[0]


def test_approval_needs_the_approver_and_approve_or_reject() -> None:
    q = questions.Question.model_validate(_approval())
    assert questions.validate_answer(q, "approve", "ana") == []
    assert questions.validate_answer(q, "reject", "ana") == []
    assert "only ana" in questions.validate_answer(q, "approve", "bo")[0]
    assert "approve or reject" in questions.validate_answer(q, "maybe", "ana")[0]
    assert len(questions.validate_answer(q, "maybe", "bo")) == 2
    orphan = questions.Question.model_validate({**_approval(), "approver": None})
    assert "no approver" in questions.validate_answer(orphan, "approve", "ana")[0]


def test_answered_and_obsolete_questions_cannot_be_answered() -> None:
    assert "already answered" in questions.validate_answer(_question(answer="x"), "y", "bo")[0]
    assert "obsolete" in questions.validate_answer(_question(obsolete=True), "y", "bo")[0]


def test_record_writes_answers(tmp_path: Path) -> None:
    path = _write(tmp_path, _q("Q-1"), _approval("Q-2"))
    answered = questions.record(path, {"Q-1": "use 3 roles", "Q-2": "approve"}, "ana", AT)
    assert [q.id for q in answered] == ["Q-1", "Q-2"]
    loaded = questions.load(path)
    assert questions.pending(loaded) == []
    assert loaded[0].answer == "use 3 roles"
    assert loaded[0].answered_by == "ana"
    assert yaml.safe_load(path.read_text())["questions"][0]["answered_at"] == AT.isoformat()


def test_record_is_all_or_nothing(tmp_path: Path) -> None:
    path = _write(tmp_path, _q("Q-1"), _approval("Q-2"))
    before = path.read_text()
    with pytest.raises(InputError) as caught:
        questions.record(path, {"Q-1": "fine", "Q-2": "approve", "Q-404": "x"}, "bo", AT)
    message = str(caught.value)
    assert "Q-2: only ana" in message and "Q-404: no such question" in message
    assert path.read_text() == before


def test_round_trip_keeps_the_skills_fields(tmp_path: Path) -> None:
    header = "# written by the clarity skills\n# keep me\n"
    item = _q("Q-1", round=3, options=["a", "b"], recommended="a", impact="high", obsolete=False)
    path = _write(tmp_path, item, _q("Q-2", "setup"), header=header)
    data = yaml.safe_load(path.read_text())
    data["extra_top_level"] = {"kept": True}
    path.write_text(header + yaml.safe_dump(data, sort_keys=False))

    questions.record(path, {"Q-2": "a monorepo"}, "bo", AT)

    text = path.read_text()
    assert text.startswith(header)
    after = yaml.safe_load(text)
    assert after["extra_top_level"] == {"kept": True}
    assert after["questions"][0] == item  # untouched, key order included
    assert list(after["questions"][0]) == list(item)
    assert after["questions"][1]["answer"] == "a monorepo"
    assert list(after["questions"][1])[:3] == ["id", "round", "kind"]


def test_details_load_default_empty_and_survive_record(tmp_path: Path) -> None:
    path = _write(
        tmp_path, _q("Q-1", details=["known: the brief", "changes: the scope"]), _q("Q-2")
    )
    first, second = questions.load(path)
    assert first.details == ["known: the brief", "changes: the scope"] and second.details == []
    questions.record(path, {"Q-1": "confirm"}, "ana", AT)
    saved = yaml.safe_load(path.read_text())["questions"][0]
    assert saved["details"] == ["known: the brief", "changes: the scope"]


# Unquoted flow lists as a model wrote them in a live run (todo-lite demo, Haiku).
_UNQUOTED = """\
questions:
  - id: Q-005
    round: 1
    kind: gap
    document: goal/requirements.md
    question: "Can two commands run at once?"
    options: [One at a time is fine, No, simultaneous commands must be handled]
    recommended: One at a time is fine
    free_text: true
    answer: null
  - id: Q-007
    round: 1
    kind: gap
    document: goal/requirements.md
    question: "How should it be tested?"
    options: [Yes, unittest with at least one test per command, Something stricter]
    recommended: Yes, unittest with at least one test per command
    free_text: true
    answer: null
  - id: Q-010
    round: 1
    kind: gap
    document: goal/requirements.md
    question: "How many entries?"
    options: [10, 10000, off]
    recommended: 10000
    free_text: false
    answer: null
"""


def test_unquoted_yes_no_and_numbers_stay_text(tmp_path: Path) -> None:
    path = tmp_path / "questions.yml"
    path.write_text(_UNQUOTED)
    q5, _, q10 = questions.load(path)
    assert q5.options == ["One at a time is fine", "No", "simultaneous commands must be handled"]
    assert q10.options == ["10", "10000", "off"] and q10.recommended == "10000"
    assert questions.validate_answer(q10, "10000", "ana") == []


def test_true_and_false_are_still_booleans(tmp_path: Path) -> None:
    path = _write(tmp_path, _q("Q-1", obsolete=True, free_text=False, options=["a"]))
    (q,) = questions.load(path)
    assert q.obsolete is True and q.free_text is False


def test_a_recommended_option_split_at_its_commas_is_joined_back(tmp_path: Path) -> None:
    path = tmp_path / "questions.yml"
    path.write_text(_UNQUOTED)
    _, q7, _ = questions.load(path)
    assert q7.options == ["Yes, unittest with at least one test per command", "Something stricter"]
    assert q7.recommended in q7.options
    questions.record(path, {"Q-005": "One at a time is fine"}, "ana", AT)
    saved = yaml.safe_load(path.read_text())["questions"][1]
    assert saved["options"] == q7.options  # the repair is saved with the next answer


def test_a_written_in_recommended_label_is_dropped(tmp_path: Path) -> None:
    """Seen in a run: options shown as "Confirm it (recommended) (recommended)"."""
    path = _write(
        tmp_path,
        _q(
            "Q-1",
            options=["Confirm it (recommended)", "Change it", "Other (Recommended) (recommended)"],
            recommended="Confirm it (recommended)",
        ),
    )
    (q,) = questions.load(path)
    assert q.options == ["Confirm it", "Change it", "Other"]
    assert q.recommended == "Confirm it"


def test_an_invalid_question_says_to_quote(tmp_path: Path) -> None:
    path = _write(tmp_path, _q("Q-1", options=[{"a": 1}]))
    with pytest.raises(InputError, match="double quotes"):
        questions.load(path)
