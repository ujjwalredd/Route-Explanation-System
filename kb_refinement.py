"""
Adaptive Knowledge Base Refinement via CBR Feedback Loop.

Detects systematic miscalibration between KB rule parameters and observed
user satisfaction, then proposes (or applies) targeted parameter updates.

Novel contribution: closing the loop between case-based experiential learning
(CBR) and symbolic rule-based knowledge (KB). No prior work in route planning
uses CBR feedback to update KB rules — existing systems only add cases or
update neural weights. See research questions in README.md.
"""

from __future__ import annotations
import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional

KB_PATH = os.path.join("data", "kb_params.json")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class MiscalibrationSignal:
    """
    One detected discrepancy between a KB parameter and observed user behaviour.

    parameter_path:  Dot-notation path, e.g. "road_stress_scores.primary"
    current_value:   Current KB value
    proposed_value:  Suggested new value after adjustment
    confidence:      [0, 1] — based on evidence count and divergence magnitude
    evidence_count:  Number of cases supporting this signal
    direction:       "increase" | "decrease"
    rationale:       Human-readable explanation of why this update is proposed
    """
    parameter_path: str
    current_value: float
    proposed_value: float
    confidence: float
    evidence_count: int
    direction: str
    rationale: str


@dataclass
class RefinementResult:
    signals: List[MiscalibrationSignal]
    applied: bool
    dry_run: bool
    cases_analyzed: int
    kb_version_before: int
    kb_version_after: int
    summary: str


# ---------------------------------------------------------------------------
# IO helpers
# ---------------------------------------------------------------------------

def load_params() -> dict:
    with open(KB_PATH) as f:
        return json.load(f)


def _save_params(params: dict) -> None:
    """Atomic write — prevents corruption on interrupted save."""
    params["last_refined"] = datetime.now().isoformat()
    params["version"] = params.get("version", 1) + 1
    tmp_path = KB_PATH + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(params, f, indent=2)
    os.replace(tmp_path, KB_PATH)


def _load_cases() -> List[dict]:
    from cbr import load_cases
    return load_cases()


# ---------------------------------------------------------------------------
# Recency filter
# ---------------------------------------------------------------------------

def _recent_cases(cases: List[dict], window_days: int) -> List[dict]:
    if window_days <= 0:
        return cases
    cutoff = datetime.now() - timedelta(days=window_days)
    result = []
    for c in cases:
        try:
            ts = datetime.fromisoformat(c.get("timestamp", ""))
            if ts >= cutoff:
                result.append(c)
        except (ValueError, TypeError):
            result.append(c)  # include cases with missing/bad timestamps
    return result or cases  # fallback: return all if window filters everything


# ---------------------------------------------------------------------------
# Analyser 1: road stress score calibration
# ---------------------------------------------------------------------------

def _analyze_stress(cases: List[dict], params: dict,
                    cfg: dict) -> List[MiscalibrationSignal]:
    """
    For each dominant_road_type, compare average user feedback against a
    neutral baseline (3.0). If users consistently rate routes higher/lower
    than the baseline, the stress score for that road type is miscalibrated.

    High avg feedback + high current stress  → stress is overestimated → decrease.
    Low  avg feedback + low  current stress  → stress is underestimated → increase.
    """
    signals: List[MiscalibrationSignal] = []
    road_stress = params.get("road_stress_scores", {})
    lr = cfg["learning_rate"]
    max_adj = cfg["max_stress_adjustment"]
    div_thresh = cfg["divergence_threshold"]

    by_type: dict = {}
    for c in cases:
        dom = c.get("profile", {}).get("dominant_road_type")
        if dom and dom in road_stress:
            by_type.setdefault(dom, []).append(c.get("feedback_score", 3))

    for road_type, scores in by_type.items():
        if len(scores) < 3:
            continue
        avg = sum(scores) / len(scores)
        divergence = 3.0 - avg          # positive → users rate lower than neutral → increase stress

        if abs(divergence) < div_thresh:
            continue

        current = road_stress[road_type]
        adj = max(-max_adj, min(max_adj, lr * divergence))
        proposed = round(max(0.5, min(5.0, current + adj)), 2)
        if proposed == current:
            continue

        confidence = round(min(1.0, abs(divergence) / 2.0 * (len(scores) / 10.0)), 2)
        direction = "increase" if adj > 0 else "decrease"
        signals.append(MiscalibrationSignal(
            parameter_path=f"road_stress_scores.{road_type}",
            current_value=current,
            proposed_value=proposed,
            confidence=confidence,
            evidence_count=len(scores),
            direction=direction,
            rationale=(
                f"{len(scores)} cases with dominant '{road_type}' roads averaged "
                f"{round(avg, 2)}/5 (neutral baseline 3.0/5). "
                f"Divergence {round(divergence, 3)} → {direction} stress score "
                f"from {current} → {proposed}."
            ),
        ))

    return signals


# ---------------------------------------------------------------------------
# Analyser 2: turn penalty calibration
# ---------------------------------------------------------------------------

def _analyze_turns(cases: List[dict], params: dict,
                   cfg: dict) -> List[MiscalibrationSignal]:
    """
    Compare feedback for routes with difficult turns vs. routes without.
    If users rate turn-heavy routes significantly lower than turn-free routes,
    the left_turn_penalty (and/or no_signal_penalty) is too lenient — increase it.
    If turn-heavy routes are rated just as highly, penalty may be too strict.
    """
    signals: List[MiscalibrationSignal] = []
    turn_penalties = params.get("turn_penalties", {})
    lr = cfg["learning_rate"]
    max_adj = cfg["max_turn_adjustment"]
    div_thresh = cfg["divergence_threshold"]

    hard_scores = [
        c.get("feedback_score", 3)
        for c in cases
        if c.get("profile", {}).get("difficult_turns", 0) > 0
    ]
    easy_scores = [
        c.get("feedback_score", 3)
        for c in cases
        if c.get("profile", {}).get("difficult_turns", 0) == 0
    ]

    if len(hard_scores) < 3 or len(easy_scores) < 3:
        return signals

    avg_hard = sum(hard_scores) / len(hard_scores)
    avg_easy = sum(easy_scores) / len(easy_scores)
    divergence = avg_easy - avg_hard  # positive → easy routes rated higher → turns are bad

    if abs(divergence) < div_thresh:
        return signals

    current = turn_penalties.get("left_turn_penalty", 0.3)
    adj = max(-max_adj, min(max_adj, lr * divergence))
    proposed = round(max(0.0, min(1.0, current + adj)), 3)
    if proposed == current:
        return signals

    confidence = round(min(1.0, abs(divergence) / 2.0 * (len(hard_scores) / 10.0)), 2)
    direction = "increase" if adj > 0 else "decrease"
    signals.append(MiscalibrationSignal(
        parameter_path="turn_penalties.left_turn_penalty",
        current_value=current,
        proposed_value=proposed,
        confidence=confidence,
        evidence_count=len(hard_scores),
        direction=direction,
        rationale=(
            f"Routes with difficult turns averaged {round(avg_hard, 2)}/5 vs. "
            f"{round(avg_easy, 2)}/5 for routes without turns "
            f"({len(hard_scores)} vs. {len(easy_scores)} cases). "
            f"Gap {round(divergence, 3)} → {direction} left_turn_penalty "
            f"from {current} → {proposed}."
        ),
    ))
    return signals


# ---------------------------------------------------------------------------
# Analyser 3: argument threshold calibration
# ---------------------------------------------------------------------------

def _analyze_thresholds(cases: List[dict], params: dict,
                        cfg: dict) -> List[MiscalibrationSignal]:
    """
    Checks whether the stress_pro_ceiling in argument_thresholds is aligned
    with the stress levels of highly-rated low-stress routes. If users rate
    routes with stress > ceiling highly, the ceiling is too conservative.
    """
    signals: List[MiscalibrationSignal] = []
    thresholds = params.get("argument_thresholds", {})
    current_ceiling = thresholds.get("stress_pro_ceiling", 2.0)

    good_ls = [
        c for c in cases
        if c.get("user_preference") == "low_stress"
        and c.get("feedback_score", 0) >= 4
    ]
    if len(good_ls) < 3:
        return signals

    avg_stress = sum(
        c.get("profile", {}).get("avg_road_stress", current_ceiling)
        for c in good_ls
    ) / len(good_ls)

    gap = abs(avg_stress - current_ceiling)
    if gap < 0.3:
        return signals

    lr = cfg["learning_rate"]
    proposed = round(max(1.0, min(3.5, current_ceiling + lr * (avg_stress - current_ceiling))), 2)
    if proposed == current_ceiling:
        return signals

    direction = "increase" if proposed > current_ceiling else "decrease"
    confidence = round(min(1.0, gap / 1.0 * (len(good_ls) / 10.0)), 2)
    signals.append(MiscalibrationSignal(
        parameter_path="argument_thresholds.stress_pro_ceiling",
        current_value=current_ceiling,
        proposed_value=proposed,
        confidence=confidence,
        evidence_count=len(good_ls),
        direction=direction,
        rationale=(
            f"{len(good_ls)} highly-rated low-stress trips averaged "
            f"{round(avg_stress, 2)} road stress. "
            f"Current ceiling is {current_ceiling} — {direction}ing to {proposed} "
            f"to better reflect observed user satisfaction."
        ),
    ))
    return signals


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_miscalibration(cases: Optional[List[dict]] = None) -> List[MiscalibrationSignal]:
    """
    Run all three analysers and return merged, deduplicated signals sorted
    by confidence descending.
    """
    if cases is None:
        cases = _load_cases()
    params = load_params()
    cfg = params.get("refinement", {
        "learning_rate": 0.05,
        "max_stress_adjustment": 0.4,
        "max_turn_adjustment": 0.2,
        "divergence_threshold": 0.4,
        "recency_window_days": 90,
    })

    windowed = _recent_cases(cases, cfg.get("recency_window_days", 90))

    signals: List[MiscalibrationSignal] = []
    signals += _analyze_stress(windowed, params, cfg)
    signals += _analyze_turns(windowed, params, cfg)
    signals += _analyze_thresholds(windowed, params, cfg)

    # Dedup by parameter_path (keep highest confidence)
    seen: dict = {}
    for s in signals:
        if s.parameter_path not in seen or s.confidence > seen[s.parameter_path].confidence:
            seen[s.parameter_path] = s

    return sorted(seen.values(), key=lambda x: -x.confidence)


def apply_refinement(
    signals: List[MiscalibrationSignal],
    dry_run: bool = False,
) -> RefinementResult:
    """
    Apply signals to kb_params.json using nested dot-notation keys.

    Each adjustment is capped at max_stress_adjustment / max_turn_adjustment
    from refinement config. Writes atomically unless dry_run=True.
    """
    params = load_params()
    version_before = params.get("version", 1)

    applied_signals = []
    for sig in signals:
        parts = sig.parameter_path.split(".")
        node = params
        try:
            for p in parts[:-1]:
                node = node[p]
            key = parts[-1]
            if key in node and not dry_run:
                node[key] = sig.proposed_value
                applied_signals.append(sig)
            elif key in node:
                applied_signals.append(sig)  # count for dry_run reporting
        except (KeyError, TypeError):
            pass  # parameter path not found — skip silently

    if not dry_run and applied_signals:
        _save_params(params)

    version_after = params.get("version", version_before + 1) if (not dry_run and applied_signals) else version_before

    if not signals:
        summary = "No miscalibration detected. Knowledge base parameters are well-aligned with observed user behaviour."
    elif dry_run:
        summary = (
            f"Dry run: {len(signals)} miscalibration signal{'s' if len(signals) != 1 else ''} detected "
            f"across {set(s.parameter_path.split('.')[0] for s in signals)}. "
            f"No changes applied. Set dry_run=false to apply."
        )
    else:
        changed = [s.parameter_path for s in applied_signals]
        summary = (
            f"Applied {len(applied_signals)} refinement{'s' if len(applied_signals) != 1 else ''}: "
            f"{', '.join(changed)}. KB version {version_before} → {version_after}."
        )

    return RefinementResult(
        signals=signals,
        applied=not dry_run and bool(applied_signals),
        dry_run=dry_run,
        cases_analyzed=len(_load_cases()),
        kb_version_before=version_before,
        kb_version_after=version_after,
        summary=summary,
    )


def analyze_and_refine(dry_run: bool = True) -> RefinementResult:
    """Convenience function: detect + apply in one call. Default is dry_run=True."""
    cases = _load_cases()
    min_cases = load_params().get("refinement", {}).get("min_cases_to_trigger", 5)
    if len(cases) < min_cases:
        return RefinementResult(
            signals=[],
            applied=False,
            dry_run=dry_run,
            cases_analyzed=len(cases),
            kb_version_before=load_params().get("version", 1),
            kb_version_after=load_params().get("version", 1),
            summary=(
                f"Insufficient cases for refinement: {len(cases)} found, "
                f"{min_cases} required. Collect more feedback and try again."
            ),
        )
    signals = detect_miscalibration(cases)
    return apply_refinement(signals, dry_run=dry_run)
