from __future__ import annotations

import argparse
import json

import dspy

import rlmbenchy.datahub.cli as datahub_cli
from rlmbenchy.datahub.types import WorkloadBundle, WorkloadTask


class _Signature(dspy.Signature):
    task: str = dspy.InputField(desc="Task.")
    answer: str = dspy.OutputField(desc="Answer.")


def _bundle(*tasks: WorkloadTask) -> WorkloadBundle:
    return WorkloadBundle(
        workload_name="demo_workload",
        tasks=list(tasks),
        tools=[],
        signature=_Signature,
        metadata={"source": "test"},
    )


def test_cmd_workloads_text_lists_available_names(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        datahub_cli,
        "AVAILABLE_WORKLOADS",
        ("demo_one", "demo_two"),
    )

    datahub_cli.cmd_workloads(argparse.Namespace(json=False))

    output = capsys.readouterr().out
    assert "demo_one" in output
    assert "demo_two" in output
    assert "2 workloads available" in output


def test_cmd_workloads_json_lists_available_names(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        datahub_cli,
        "AVAILABLE_WORKLOADS",
        ("demo_one", "demo_two"),
    )

    datahub_cli.cmd_workloads(argparse.Namespace(json=True))

    payload = json.loads(capsys.readouterr().out)
    assert payload == [{"name": "demo_one"}, {"name": "demo_two"}]


def test_cmd_tasks_text_uses_task_inputs(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(
        datahub_cli,
        "load_workload",
        lambda *args, **kwargs: _bundle(
            WorkloadTask(id="t1", inputs={"task": "Solve 2+2."}, answer="4")
        ),
    )

    datahub_cli.cmd_tasks(
        argparse.Namespace(
            workload="demo_workload",
            limit=None,
            task_id=None,
            option=[],
            json=False,
        )
    )

    output = capsys.readouterr().out
    assert "Workload: demo_workload" in output
    assert "Solve 2+2." in output
    assert "[ans: 4]" in output


def test_cmd_tasks_task_id_load_ignores_limit(monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    def _load_workload(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return _bundle(
            WorkloadTask(id="t2", inputs={"task": "Compute 3*3."}, answer="9")
        )

    monkeypatch.setattr(datahub_cli, "load_workload", _load_workload)

    datahub_cli.cmd_tasks(
        argparse.Namespace(
            workload="demo_workload",
            limit=1,
            task_id=" t2 ",
            option=[],
            json=False,
        )
    )

    output = capsys.readouterr().out
    assert "Compute 3*3." in output
    assert captured["args"] == ("demo_workload",)
    assert captured["kwargs"] == {
        "task_limit": None,
        "task_id": "t2",
        "options": {},
    }


def test_cmd_tasks_json_outputs_full_rows(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        datahub_cli,
        "load_workload",
        lambda *args, **kwargs: _bundle(
            WorkloadTask(id="t1", inputs={"task": "Solve 2+2."}, answer="4"),
            WorkloadTask(id="t2", inputs={"task": "Compute 3*3."}, answer="9"),
        ),
    )

    datahub_cli.cmd_tasks(
        argparse.Namespace(
            workload="demo_workload",
            limit=None,
            task_id=None,
            option=[],
            json=True,
        )
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["workload"] == "demo_workload"
    assert payload["task_count"] == 2
    assert [row["id"] for row in payload["tasks"]] == ["t1", "t2"]
    assert payload["tasks"][0]["answer"] == "4"
    assert payload["tasks"][0]["prompt_preview"] == "Solve 2+2."


def test_cmd_task_json_outputs_inputs_and_prompt_preview(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(
        datahub_cli,
        "load_workload",
        lambda *args, **kwargs: _bundle(
            WorkloadTask(
                id="t2",
                inputs={"question": "Which option is correct?", "docs_total": 3},
                answer="B",
                metadata={"query_id": "q1"},
            )
        ),
    )

    datahub_cli.cmd_task(
        argparse.Namespace(
            workload="demo_workload",
            task_id="t2",
            option=[],
            json=True,
        )
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["id"] == "t2"
    assert payload["inputs"] == {
        "question": "Which option is correct?",
        "docs_total": 3,
    }
    assert payload["prompt_preview"] == "Which option is correct?"
    assert payload["answer"] == "B"
    assert payload["metadata"] == {"query_id": "q1"}


def test_cmd_task_text_shows_inputs_and_answer(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        datahub_cli,
        "load_workload",
        lambda *args, **kwargs: _bundle(
            WorkloadTask(
                id="t3",
                inputs={"question": "What is 7+5?"},
                answer="12",
            )
        ),
    )

    datahub_cli.cmd_task(
        argparse.Namespace(
            workload="demo_workload",
            task_id="t3",
            option=[],
            json=False,
        )
    )

    output = capsys.readouterr().out
    assert "Task: t3" in output
    assert "Workload: demo_workload" in output
    assert "What is 7+5?" in output
    assert "Answer: 12" in output


def test_cmd_task_missing_task_exits_with_error(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        datahub_cli,
        "load_workload",
        lambda *args, **kwargs: _bundle(),
    )

    try:
        datahub_cli.cmd_task(
            argparse.Namespace(
                workload="demo_workload",
                task_id="missing",
                option=[],
                json=False,
            )
        )
    except SystemExit as exc:
        assert exc.code == 1
    err = capsys.readouterr().err
    assert "No task found" in err
