"""Aggregate eval results into summary metrics."""

from __future__ import annotations

import math
from typing import Any


def aggregate_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute summary metrics from a list of task results.

    Parameters
    ----------
    results : list[dict]
        Each dict has ``trials`` (list of trial outcomes with ``passed``,
        ``score``, ``elapsed_s``).

    Returns
    -------
    dict with keys:
        total_tasks, total_passed, pass_at_1, pass_at_k, pass_pow_k,
        avg_score, avg_latency_s, precision, recall
    """
    total_tasks = len(results)
    if total_tasks == 0:
        return _empty_report()

    pass_at_1_count = 0
    pass_at_k_count = 0
    all_pass_count = 0
    all_scores: list[float] = []
    all_latencies: list[float] = []
    total_expected = 0
    total_correct = 0
    total_extracted = 0

    for task_result in results:
        trials = task_result.get("trials", [])
        if not trials:
            continue

        # pass@1: first trial passes
        if trials[0].get("passed", False):
            pass_at_1_count += 1

        # pass@k: any trial passes
        any_passed = any(t.get("passed", False) for t in trials)
        if any_passed:
            pass_at_k_count += 1

        # pass^k: all trials pass
        if all(t.get("passed", False) for t in trials):
            all_pass_count += 1

        for t in trials:
            all_scores.append(t.get("score", 0.0))
            if "elapsed_s" in t:
                all_latencies.append(t["elapsed_s"])

            # Precision/recall from error counts if available
            errors = t.get("errors", [])
            result_dict = t.get("result", {})
            expected_dict = task_result.get("expected", {})
            if expected_dict:
                total_expected += len(expected_dict)
                total_extracted += len(result_dict)
                total_correct += len(expected_dict) - len(
                    [e for e in errors if e.startswith("missing key")]
                )

    avg_score = sum(all_scores) / len(all_scores) if all_scores else 0.0
    avg_latency = sum(all_latencies) / len(all_latencies) if all_latencies else 0.0
    precision = total_correct / total_extracted if total_extracted else 0.0
    recall = total_correct / total_expected if total_expected else 0.0

    k = len(results[0].get("trials", [])) if results else 1

    return {
        "total_tasks": total_tasks,
        "total_passed": pass_at_k_count,
        "pass_at_1": pass_at_1_count / total_tasks,
        "pass_at_k": pass_at_k_count / total_tasks,
        "pass_pow_k": all_pass_count / total_tasks,
        "k": k,
        "avg_score": round(avg_score, 4),
        "avg_latency_s": round(avg_latency, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
    }


def _empty_report() -> dict[str, Any]:
    return {
        "total_tasks": 0,
        "total_passed": 0,
        "pass_at_1": 0.0,
        "pass_at_k": 0.0,
        "pass_pow_k": 0.0,
        "k": 0,
        "avg_score": 0.0,
        "avg_latency_s": 0.0,
        "precision": 0.0,
        "recall": 0.0,
    }
