"""Deterministic (code-based) graders for eval tasks."""

from __future__ import annotations

from typing import Any


def check_extraction(
    result: dict[str, Any],
    expected: dict[str, Any],
    *,
    absent_keys: list[str] | None = None,
) -> dict[str, Any]:
    """Deep-compare extracted metadata against expected values.

    Parameters
    ----------
    result : dict
        The metadata dict produced by the extraction function.
    expected : dict
        The ground-truth metadata dict.
    absent_keys : list[str] | None
        Top-level keys that must NOT appear in the result.

    Returns
    -------
    dict with keys:
        passed : bool
        score  : float   (0.0 – 1.0, partial credit)
        errors : list[str]
    """
    errors: list[str] = []
    total_checks = 0
    passed_checks = 0

    # Check expected keys
    for key, exp_value in expected.items():
        total_checks += 1
        if key not in result:
            errors.append(f"missing key: {key}")
            continue

        actual = result[key]
        if isinstance(exp_value, dict) and isinstance(actual, dict):
            sub = _compare_dicts(actual, exp_value, prefix=key)
            if sub:
                errors.extend(sub)
            else:
                passed_checks += 1
        elif isinstance(exp_value, list) and isinstance(actual, list):
            if not _lists_match(actual, exp_value):
                errors.append(f"{key}: expected {exp_value!r}, got {actual!r}")
            else:
                passed_checks += 1
        elif actual != exp_value:
            errors.append(f"{key}: expected {exp_value!r}, got {actual!r}")
        else:
            passed_checks += 1

    # Absence checks
    for key in absent_keys or []:
        total_checks += 1
        if key in result and result[key]:
            errors.append(f"key should be absent: {key} (got {result[key]!r})")
        else:
            passed_checks += 1

    score = passed_checks / total_checks if total_checks else 1.0
    return {"passed": len(errors) == 0, "score": score, "errors": errors}


def _compare_dicts(actual: dict, expected: dict, prefix: str = "") -> list[str]:
    errors: list[str] = []
    for k, v in expected.items():
        path = f"{prefix}.{k}" if prefix else k
        if k not in actual:
            errors.append(f"missing key: {path}")
        elif isinstance(v, dict) and isinstance(actual[k], dict):
            errors.extend(_compare_dicts(actual[k], v, path))
        elif actual[k] != v:
            errors.append(f"{path}: expected {v!r}, got {actual[k]!r}")
    return errors


def _lists_match(actual: list, expected: list) -> bool:
    if len(actual) != len(expected):
        return False
    for a, e in zip(actual, expected):
        if isinstance(a, dict) and isinstance(e, dict):
            if _compare_dicts(a, e):
                return False
        elif a != e:
            return False
    return True


def check_api_response(
    response,
    expected_status: int,
    expected_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate an HTTP response against expectations.

    Parameters
    ----------
    response : httpx.Response
        The response object to check.
    expected_status : int
        Expected HTTP status code.
    expected_body : dict | None
        If provided, check that the response JSON contains these key/value pairs.

    Returns
    -------
    dict with keys: passed, errors
    """
    errors: list[str] = []

    if response.status_code != expected_status:
        errors.append(
            f"status: expected {expected_status}, got {response.status_code}"
        )

    if expected_body is not None:
        try:
            body = response.json()
        except Exception:
            errors.append("response body is not valid JSON")
            return {"passed": False, "errors": errors}

        for key, value in expected_body.items():
            if key not in body:
                errors.append(f"missing key in body: {key}")
            elif body[key] != value:
                errors.append(f"body.{key}: expected {value!r}, got {body[key]!r}")

    return {"passed": len(errors) == 0, "errors": errors}


async def check_db_state(
    db,
    query: str,
    expected: list[dict[str, Any]],
) -> dict[str, Any]:
    """Verify SQLite state matches expectations.

    Parameters
    ----------
    db : aiosqlite.Connection
        The database connection.
    query : str
        SQL SELECT query to run.
    expected : list[dict]
        Expected rows (each as a dict).

    Returns
    -------
    dict with keys: passed, errors
    """
    cursor = await db.execute(query)
    rows = [dict(r) for r in await cursor.fetchall()]
    errors: list[str] = []

    if len(rows) != len(expected):
        errors.append(f"row count: expected {len(expected)}, got {len(rows)}")
        return {"passed": False, "errors": errors}

    for i, (row, exp) in enumerate(zip(rows, expected)):
        for key, value in exp.items():
            if key not in row:
                errors.append(f"row {i}: missing column {key}")
            elif row[key] != value:
                errors.append(
                    f"row {i}.{key}: expected {value!r}, got {row[key]!r}"
                )

    return {"passed": len(errors) == 0, "errors": errors}
