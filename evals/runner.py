"""CLI eval runner — loads YAML task files and executes eval trials.

Usage:
    python -m evals.runner --all
    python -m evals.runner --suite extraction
    python -m evals.runner --suite extraction --trials 5
    python -m evals.runner --suite extraction --report results/report.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

import yaml

from .graders.deterministic import check_extraction
from .report import aggregate_results

logger = logging.getLogger(__name__)

TASKS_DIR = Path(__file__).parent / "tasks"


def load_tasks(suite: str | None = None) -> list[dict[str, Any]]:
    """Load task YAML files from the tasks/ directory.

    If *suite* is given, only load from ``tasks/{suite}/``.
    Otherwise load from all subdirectories.
    """
    tasks: list[dict[str, Any]] = []
    if suite:
        search_dirs = [TASKS_DIR / suite]
    else:
        search_dirs = [d for d in TASKS_DIR.iterdir() if d.is_dir()]

    for d in search_dirs:
        if not d.exists():
            logger.warning("Task directory not found: %s", d)
            continue
        for yaml_file in sorted(d.glob("*.yaml")):
            with open(yaml_file) as f:
                task = yaml.safe_load(f)
            task.setdefault("id", yaml_file.stem)
            task.setdefault("suite", d.name)
            task["_path"] = str(yaml_file)
            tasks.append(task)

    return tasks


def run_extraction_trial(task: dict[str, Any]) -> dict[str, Any]:
    """Run a single extraction trial: grade expected vs actual.

    Extraction is now done by the Claude agent via the capture_metadata tool,
    so this runner cannot replay it offline.  It grades the *expected* dict
    against itself (score 1.0) as a smoke-check that the YAML cases are
    well-formed.  Real extraction accuracy is tested in
    evals/tasks/extraction/test_agent_extraction.py (marked @llm).
    """
    expected = task.get("expected", {})
    absent_keys = task.get("absent_keys", [])

    t0 = time.perf_counter()
    # Use expected as the "result" — the real agent test lives in pytest
    result = expected
    elapsed = time.perf_counter() - t0

    grade = check_extraction(result, expected, absent_keys=absent_keys)
    return {
        "result": result,
        "elapsed_s": round(elapsed, 4),
        **grade,
    }


def run_task(task: dict[str, Any], trials: int = 3) -> dict[str, Any]:
    """Run multiple trials for a single task and collect results."""
    task_type = task.get("type", "extraction")
    trial_results: list[dict[str, Any]] = []

    for trial_num in range(trials):
        if task_type == "extraction":
            outcome = run_extraction_trial(task)
        else:
            logger.warning("Unknown task type: %s — skipping", task_type)
            outcome = {"passed": False, "score": 0.0, "errors": [f"unknown type: {task_type}"]}

        outcome["trial"] = trial_num + 1
        trial_results.append(outcome)

    return {
        "task_id": task["id"],
        "suite": task.get("suite", "unknown"),
        "type": task_type,
        "trials": trial_results,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run metadata-capture evals")
    parser.add_argument("--all", action="store_true", help="Run all suites")
    parser.add_argument("--suite", type=str, help="Run a specific suite")
    parser.add_argument("--trials", type=int, default=3, help="Trials per task")
    parser.add_argument("--report", type=str, help="Write JSON report to file")
    args = parser.parse_args(argv)

    if not args.all and not args.suite:
        parser.error("Specify --all or --suite <name>")

    suite = None if args.all else args.suite
    tasks = load_tasks(suite)

    if not tasks:
        print("No tasks found.", file=sys.stderr)
        sys.exit(1)

    print(f"Running {len(tasks)} task(s), {args.trials} trial(s) each …")

    all_results: list[dict[str, Any]] = []
    for task in tasks:
        print(f"  {task['suite']}/{task['id']} … ", end="", flush=True)
        result = run_task(task, trials=args.trials)
        passes = sum(1 for t in result["trials"] if t["passed"])
        print(f"{passes}/{args.trials} passed")
        all_results.append(result)

    report = aggregate_results(all_results)
    print(f"\nSummary: {report['total_passed']}/{report['total_tasks']} tasks passed")
    print(f"  pass@1={report['pass_at_1']:.2%}  avg_score={report['avg_score']:.3f}")

    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w") as f:
            json.dump({"tasks": all_results, "summary": report}, f, indent=2)
        print(f"Report written to {report_path}")


if __name__ == "__main__":
    main()
