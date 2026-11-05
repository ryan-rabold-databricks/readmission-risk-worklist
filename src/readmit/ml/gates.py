"""Champion/challenger promotion gates (DECISIONS.md #30).

- No champion yet: the challenger must reach min_auc with a calibration slope inside
  [slope_min, slope_max].
- Champion exists: both are evaluated on the challenger's test window; the challenger
  must keep AUC within auc_tolerance of the champion and have a Brier score no worse.
"""

from __future__ import annotations

from dataclasses import dataclass

from readmit.ml.metrics import EvalMetrics


@dataclass(frozen=True)
class Gates:
    min_auc: float = 0.68
    slope_min: float = 0.8
    slope_max: float = 1.2
    auc_tolerance: float = 0.005


@dataclass(frozen=True)
class GateDecision:
    promote: bool
    reasons: list[str]


def decide(challenger: EvalMetrics, champion: EvalMetrics | None, gates: Gates) -> GateDecision:
    reasons: list[str] = []
    if champion is None:
        auc_ok = challenger.auc >= gates.min_auc
        slope_ok = gates.slope_min <= challenger.calibration_slope <= gates.slope_max
        reasons.append(f"AUC {challenger.auc:.4f} {'>=' if auc_ok else '<'} minimum {gates.min_auc}")
        reasons.append(
            f"calibration slope {challenger.calibration_slope:.3f} "
            f"{'inside' if slope_ok else 'outside'} [{gates.slope_min}, {gates.slope_max}]"
        )
        return GateDecision(auc_ok and slope_ok, reasons)
    floor = champion.auc - gates.auc_tolerance
    auc_ok = challenger.auc >= floor
    brier_ok = challenger.brier <= champion.brier
    reasons.append(
        f"AUC {challenger.auc:.4f} vs champion {champion.auc:.4f} "
        f"({'>=' if auc_ok else '<'} floor {floor:.4f})"
    )
    reasons.append(
        f"Brier {challenger.brier:.5f} vs champion {champion.brier:.5f} "
        f"({'no worse' if brier_ok else 'worse'})"
    )
    return GateDecision(auc_ok and brier_ok, reasons)
