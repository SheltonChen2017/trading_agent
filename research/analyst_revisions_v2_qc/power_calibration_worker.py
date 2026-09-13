"""Pure Decimal worker for one ARV2 nuisance-calibration cross-section.

The QC facade supplies already authenticated preoutcome rows and ephemeral
market observations.  This module returns one beta state and never retains or
returns a security-level outcome.
"""
from __future__ import annotations

import hashlib
import json
from decimal import (
    Context, Decimal, DivisionByZero, InvalidOperation, Overflow,
    ROUND_HALF_EVEN, localcontext,
)

INPUT_ROW_SCHEMA = "arv2-accepted-risk-power-calibration-session-v1"
OUTPUT_ROW_SCHEMA = "arv2-accepted-risk-power-calibration-beta-state-v1"
RANK_RELATIVE_THRESHOLD = Decimal("1e-20")


def _canonical(value):
    return (
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _context():
    return Context(
        prec=50, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999,
        capitals=1, clamp=0, flags=[],
        traps=[DivisionByZero, InvalidOperation, Overflow],
    )


def _decimal(value, name, positive=False):
    if type(value) is not str or not value or value != value.strip():
        raise ValueError(name + " is not exact Decimal text")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(name + " is not Decimal") from exc
    if not result.is_finite() or (positive and result <= 0):
        raise ValueError(name + " is outside its domain")
    return result


def _text(value):
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def _stable_sum(values):
    with localcontext(_context()):
        result = Decimal(0)
        for value in sorted(
            tuple(values), key=lambda item: (item.copy_abs(), item)
        ):
            result = +(result + value)
        return result


def _dot(left, right):
    if len(left) != len(right):
        raise ValueError("dot vectors changed length")
    with localcontext(_context()):
        return _stable_sum(+(a * b) for a, b in zip(left, right))


def _fit(rows):
    industries = tuple(sorted({row["industry_id"] for row in rows}))
    if not industries:
        return None, "empty_date"
    levels = industries[1:]
    parameter_count = 1 + 2 + 27 + len(levels)
    if len(rows) <= parameter_count + 20:
        return None, "not_strictly_more_than_parameter_count_plus_20"
    component_counts = {}
    for row in rows:
        component = row["common_event_component_id"]
        component_counts[component] = component_counts.get(component, 0) + 1
    if not component_counts:
        return None, "no_common_event_components"
    design = []
    outcomes = []
    weights = []
    with localcontext(_context()):
        for row in rows:
            score = row["firm_specific_score"]
            design.append((
                Decimal(1), max(score, Decimal(0)), min(score, Decimal(0)),
                *row["continuous_controls"],
                *(Decimal(item) for item in row["binary_controls"]),
                Decimal(row["active_event_indicator"]), row["jump"],
                *(Decimal(row["industry_id"] == level) for level in levels),
            ))
            outcomes.append(row["excess_return"])
            weights.append(+(
                Decimal(1) / Decimal(len(component_counts))
                / Decimal(component_counts[row["common_event_component_id"]])
            ))
        columns = tuple(
            tuple(design[row][column] for row in range(len(rows)))
            for column in range(parameter_count)
        )
        roots = tuple(item.sqrt() for item in weights)
        columns = tuple(
            tuple(+(item * root) for item, root in zip(column, roots))
            for column in columns
        )
        outcome = tuple(+(item * root) for item, root in zip(outcomes, roots))
        q_columns = []
        matrix = [
            [Decimal(0) for _ in range(parameter_count)]
            for _ in range(parameter_count)
        ]
        diagonals = []
        for column_index, source in enumerate(columns):
            vector = list(source)
            for prior, basis in enumerate(q_columns):
                projection = _dot(basis, tuple(vector))
                matrix[prior][column_index] = projection
                vector = [
                    +(item - projection * unit)
                    for item, unit in zip(vector, basis)
                ]
            square = _dot(tuple(vector), tuple(vector))
            if square <= 0:
                return None, "rank_deficient_design"
            diagonal = square.sqrt()
            diagonals.append(diagonal)
            matrix[column_index][column_index] = diagonal
            q_columns.append(tuple(+(item / diagonal) for item in vector))
        largest = max(diagonals)
        if any(item <= +(largest * RANK_RELATIVE_THRESHOLD) for item in diagonals):
            return None, "rank_deficient_design"
        qty = [_dot(column, outcome) for column in q_columns]
        beta = [Decimal(0) for _ in range(parameter_count)]
        for row_index in range(parameter_count - 1, -1, -1):
            tail = _stable_sum(
                +(matrix[row_index][column] * beta[column])
                for column in range(row_index + 1, parameter_count)
            )
            beta[row_index] = +(
                (qty[row_index] - tail) / matrix[row_index][row_index]
            )
    return beta[1], None


def _jump(decision, entry, minute_observations):
    if decision["structural_zero"]:
        return Decimal(0)
    contributions = decision["contributions"]
    if not contributions:
        return Decimal(0)
    numerator = Decimal(0)
    denominator = Decimal(0)
    with localcontext(_context()):
        for contribution in contributions:
            publication = contribution["publication_at_utc"]
            if publication is None:
                return None
            observed = minute_observations.get((decision["security_id"], publication))
            if observed is None:
                return None
            price = _decimal(observed, "publication price", positive=True)
            weight = _decimal(
                contribution["firm_absolute_decayed_weight"],
                "contribution weight", positive=True,
            )
            numerator += weight * abs(entry / price - Decimal(1))
            denominator += weight
        return None if denominator <= 0 else +(numerator / denominator)


def _terminal_return(decision, daily_observations, session, exit_session):
    """Apply a declared terminal disposition before any ordinary price."""
    terminal = decision["terminal_disposition"]
    if terminal is not None:
        if type(terminal) is not dict or set(terminal) != {
            "disposition", "stock_return", "reason",
            "terminal_lineage_sha256", "available_at_utc",
        }:
            raise ValueError("terminal disposition fields changed")
        if terminal["disposition"] == "terminal_payoff":
            if terminal["reason"] is not None:
                raise ValueError("terminal payoff unexpectedly has a reason")
            return _decimal(terminal["stock_return"], "terminal payoff"), None
        if terminal["disposition"] == "named_terminal_refusal":
            if type(terminal["reason"]) is not str or not terminal["reason"]:
                raise ValueError("named terminal refusal lost its reason")
            if terminal["stock_return"] is not None:
                raise ValueError("named terminal refusal acquired a payoff")
            return None, terminal["reason"]
        raise ValueError("terminal disposition changed")
    start = daily_observations.get((decision["security_id"], session))
    end = daily_observations.get((decision["security_id"], exit_session))
    if start is None or end is None:
        return None, "missing_stock_total_return_open"
    with localcontext(_context()):
        return +(
            _decimal(end, "stock exit open", positive=True)
            / _decimal(start, "stock entry open", positive=True)
            - Decimal(1)
        ), None


def evaluate_calibration_session(
    input_row, daily_observations, minute_observations,
):
    """Return one aggregate beta terminal, never security-level outcomes."""
    if type(input_row) is not dict or input_row.get("schema") != INPUT_ROW_SCHEMA:
        raise ValueError("calibration input session changed")
    seed = dict(input_row)
    input_hash = seed.pop("input_session_sha256", None)
    if input_hash != hashlib.sha256(_canonical(seed)).hexdigest():
        raise ValueError("calibration input session hash changed")
    session = input_row["decision_session"]
    component_count = input_row["connected_component_count"]
    disposition = input_row["preoutcome_disposition"]
    state = "refused" if disposition == "refused" else "missing"
    reason = (
        "preoutcome_named_refusal_present"
        if disposition == "refused" else "empty_preoutcome_cross_section"
    )
    beta = None
    if disposition == "ready":
        # A lifecycle-derived named terminal refusal is authoritative even if
        # ordinary stock or benchmark bars happen to exist.  Do not touch any
        # numeric market observation before honoring that terminal.
        for decision in input_row["decisions"]:
            terminal = decision["terminal_disposition"]
            if terminal is not None:
                # Validate the entire terminal object before reading even its
                # discriminator.  A named refusal is then terminal for the
                # whole date before benchmark or ordinary stock-bar access.
                stock_return, terminal_reason = _terminal_return(
                    decision, {}, session, input_row["exit_session"]
                )
                if terminal_reason is not None:
                    state = "refused"
                    reason = terminal_reason
                    break
                if stock_return is None:
                    raise ValueError("terminal payoff disappeared")
        else:
            terminal_reason = None
        if terminal_reason is not None:
            benchmark = None
        else:
            benchmark = input_row["benchmark_security_id"]
        start = None if benchmark is None else daily_observations.get((benchmark, session))
        end = None if benchmark is None else daily_observations.get(
            (benchmark, input_row["exit_session"])
        )
        if terminal_reason is not None:
            pass
        elif start is None or end is None:
            reason = "missing_benchmark_total_return_open"
        else:
            with localcontext(_context()):
                benchmark_return = +(
                    _decimal(end, "benchmark exit open", positive=True)
                    / _decimal(start, "benchmark entry open", positive=True)
                    - Decimal(1)
                )
            rows = []
            outcome_reason = None
            for decision in input_row["decisions"]:
                stock_return, terminal_reason = _terminal_return(
                    decision, daily_observations, session, input_row["exit_session"]
                )
                if terminal_reason is not None:
                    outcome_reason = terminal_reason
                    state = "refused"
                    break
                entry_text = daily_observations.get(
                    (decision["security_id"], session)
                )
                jump = None if entry_text is None else _jump(
                    decision, _decimal(entry_text, "entry open", positive=True),
                    minute_observations,
                )
                if jump is None:
                    outcome_reason = "missing_publication_or_entry_price"
                    break
                with localcontext(_context()):
                    excess = +(stock_return - benchmark_return)
                rows.append({
                    "industry_id": decision["industry_id"],
                    "common_event_component_id": decision["common_event_component_id"],
                    "firm_specific_score": _decimal(
                        decision["firm_specific_score"], "firm score"
                    ),
                    "continuous_controls": tuple(
                        _decimal(item, "continuous control")
                        for item in decision["continuous_controls"]
                    ),
                    "binary_controls": tuple(decision["binary_controls"]),
                    "active_event_indicator": int(not decision["structural_zero"]),
                    "jump": jump, "excess_return": excess,
                })
            if outcome_reason is not None:
                reason = outcome_reason
            else:
                beta, reason = _fit(tuple(rows))
                state = "valid" if beta is not None else "refused"
    record = {
        "schema": OUTPUT_ROW_SCHEMA,
        "decision_session": session,
        "state": state,
        "beta_value": None if beta is None else _text(beta),
        "connected_component_count": component_count,
        "reason": None if beta is not None else reason,
        "input_session_sha256": input_hash,
    }
    return {
        **record,
        "output_lineage_sha256": hashlib.sha256(_canonical(record)).hexdigest(),
    }


__all__ = ["evaluate_calibration_session"]
