from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from compose.workflows import loader

SIMPLE = """\
workflow:
  id: {id}
  name: {name}
steps:
  - id: a
    run: echo hi
"""


def write_wf(folder: Path, wf_id: str, name: str = "Custom", extra: str = "") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "workflow.yml").write_text(SIMPLE.format(id=wf_id, name=name) + extra)
    return folder


def test_builtins_all_valid() -> None:
    items = loader.list_workflows(None)
    assert {i.id for i in items} == {"full-cycle", "quick", "bugfix"}
    assert all(i.error is None and i.source == "builtin" for i in items)


def test_resolve_builtin(git_repo: Path) -> None:
    loaded = loader.resolve("quick", git_repo)
    assert loaded.source == "builtin" and loaded.id == "quick"


def test_repo_shadows_builtin(git_repo: Path) -> None:
    write_wf(git_repo / ".compose/workflows/quick", "quick", "Our quick")
    loaded = loader.resolve("quick", git_repo)
    assert loaded.source == "repo"
    assert loaded.definition.workflow.name == "Our quick"
    listing = {(i.id, i.source): i for i in loader.list_workflows(git_repo)}
    assert listing[("quick", "repo")].shadowed is False
    assert listing[("quick", "builtin")].shadowed is True


def test_resolve_by_path(tmp_path: Path) -> None:
    folder = write_wf(tmp_path / "flow", "flow")
    assert loader.resolve(str(folder), None).id == "flow"
    assert loader.resolve(str(folder / "workflow.yml"), None).source == "file"
    single = tmp_path / "one.yml"
    single.write_text(SIMPLE.format(id="one", name="One"))
    assert loader.resolve(str(single), None).id == "one"


def test_resolve_errors(git_repo: Path, tmp_path: Path) -> None:
    with pytest.raises(loader.WorkflowError, match="No workflow 'ghost'"):
        loader.resolve("ghost", git_repo)
    write_wf(git_repo / ".compose/workflows/mismatch", "other")
    with pytest.raises(loader.WorkflowError, match="folder is 'mismatch'"):
        loader.resolve("mismatch", git_repo)
    with pytest.raises(loader.WorkflowError, match="does not exist"):
        loader.resolve(str(tmp_path / "nope.yml"), None)
    (tmp_path / "empty").mkdir()
    with pytest.raises(loader.WorkflowError, match="has no workflow.yml"):
        loader.load_path(tmp_path / "empty")


def test_invalid_files_report_location(tmp_path: Path) -> None:
    bad_yaml = tmp_path / "bad.yml"
    bad_yaml.write_text("workflow: [unclosed")
    with pytest.raises(loader.WorkflowError, match="invalid YAML"):
        loader.load_path(bad_yaml)
    bad = tmp_path / "bad2.yml"
    bad.write_text(SIMPLE.format(id="x", name="X") + "  - id: a\n    run: again\n")
    with pytest.raises(loader.WorkflowError) as err:
        loader.load_path(bad)
    assert str(bad) in str(err.value) and "duplicate step id 'a'" in str(err.value)


def test_list_includes_invalid(git_repo: Path) -> None:
    folder = git_repo / ".compose/workflows/broken"
    folder.mkdir(parents=True)
    (folder / "workflow.yml").write_text("workflow: {id: broken}\n")
    broken = [i for i in loader.list_workflows(git_repo) if i.id == "broken"][0]
    assert broken.workflow is None and broken.error and "invalid workflow" in broken.error


def test_add_folder_copies_companions(git_repo: Path, tmp_path: Path) -> None:
    src = write_wf(tmp_path / "src", "mine")
    (src / "scripts").mkdir()
    (src / "scripts" / "check.sh").write_text("#!/bin/sh\n")
    loaded = loader.add_workflow(git_repo, str(src))
    assert loaded.source == "repo"
    assert (git_repo / ".compose/workflows/mine/scripts/check.sh").exists()
    with pytest.raises(loader.WorkflowError, match="--force"):
        loader.add_workflow(git_repo, str(src))
    loader.add_workflow(git_repo, str(src), force=True)


def test_add_single_file(git_repo: Path, tmp_path: Path) -> None:
    single = tmp_path / "anything.yaml"
    single.write_text(SIMPLE.format(id="single", name="S"))
    loader.add_workflow(git_repo, str(single))
    assert (git_repo / ".compose/workflows/single/workflow.yml").exists()


def test_add_invalid_is_not_installed(git_repo: Path, tmp_path: Path) -> None:
    bad = tmp_path / "bad.yml"
    bad.write_text("workflow: {id: bad, name: B}\nsteps: []\n")
    with pytest.raises(loader.WorkflowError):
        loader.add_workflow(git_repo, str(bad))
    assert not (git_repo / ".compose/workflows/bad").exists()


def test_add_from_url(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url: str, **_: Any) -> httpx.Response:
        return httpx.Response(
            200, text=SIMPLE.format(id="remote", name="R"), request=httpx.Request("GET", url)
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    loaded = loader.add_workflow(git_repo, "https://example.invalid/wf.yml")
    assert loaded.id == "remote" and loaded.source == "repo"


def test_add_from_url_http_error(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url: str, **_: Any) -> httpx.Response:
        return httpx.Response(404, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    with pytest.raises(loader.WorkflowError, match="Cannot download"):
        loader.add_workflow(git_repo, "https://example.invalid/wf.yml")


def test_remove(git_repo: Path, tmp_path: Path) -> None:
    loader.add_workflow(git_repo, str(write_wf(tmp_path / "s", "gone")))
    loader.remove_workflow(git_repo, "gone")
    assert not (git_repo / ".compose/workflows/gone").exists()
    with pytest.raises(loader.WorkflowError, match="built in"):
        loader.remove_workflow(git_repo, "quick")
    with pytest.raises(loader.WorkflowError, match="No installed workflow"):
        loader.remove_workflow(git_repo, "ghost")
