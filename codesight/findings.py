from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ValueEnum(str, Enum):
    @classmethod
    def parse(cls, value: str | ValueEnum) -> Any:
        if isinstance(value, cls):
            return value
        normalized = str(value).lower().replace("-", "_")
        for member in cls:
            if member.value == normalized or member.name.lower() == normalized:
                return member
        allowed = ", ".join(member.value for member in cls)
        raise ValueError(f"Invalid {cls.__name__}: {value!r}. Expected one of: {allowed}")


class Severity(ValueEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Verdict(ValueEnum):
    EXPLOITABLE = "exploitable"
    LIKELY_EXPLOITABLE = "likely_exploitable"
    UNCERTAIN = "uncertain"
    PROBABLY_FALSE_POSITIVE = "probably_false_positive"
    NOT_EXPLOITABLE = "not_exploitable"


class Confidence(ValueEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


SERIOUS_VERDICTS = {
    Verdict.EXPLOITABLE,
    Verdict.LIKELY_EXPLOITABLE,
}


@dataclass
class EvidencePathStep:
    location: str
    evidence: str
    kind: str = "code"

    def __post_init__(self) -> None:
        if not self.location.strip():
            raise ValueError("Evidence path step needs a location")
        if not self.evidence.strip():
            raise ValueError("Evidence path step needs evidence")

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "location": self.location,
            "evidence": self.evidence,
        }


@dataclass
class ExploitabilityScore:
    attacker_control: int = 0
    reachability: int = 0
    missing_guard: int = 0
    impact: int = 0
    exploit_complexity: int = 0
    confidence_bonus: int = 0

    def __post_init__(self) -> None:
        self._check_range("attacker_control", self.attacker_control, 25)
        self._check_range("reachability", self.reachability, 20)
        self._check_range("missing_guard", self.missing_guard, 20)
        self._check_range("impact", self.impact, 20)
        self._check_range("exploit_complexity", self.exploit_complexity, 10)
        self._check_range("confidence_bonus", self.confidence_bonus, 5)

    @staticmethod
    def _check_range(name: str, value: int, maximum: int) -> None:
        if not isinstance(value, int):
            raise TypeError(f"{name} must be an int")
        if value < 0 or value > maximum:
            raise ValueError(f"{name} must be between 0 and {maximum}")

    @property
    def total(self) -> int:
        return (
            self.attacker_control
            + self.reachability
            + self.missing_guard
            + self.impact
            + self.exploit_complexity
            + self.confidence_bonus
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "total": self.total,
            "attacker_control": self.attacker_control,
            "reachability": self.reachability,
            "missing_guard": self.missing_guard,
            "impact": self.impact,
            "exploit_complexity": self.exploit_complexity,
            "confidence_bonus": self.confidence_bonus,
        }


@dataclass
class VerifiedFinding:
    id: str
    title: str
    verdict: Verdict | str
    severity: Severity | str
    confidence: Confidence | str
    file_path: str
    start_line: int | None = None
    end_line: int | None = None
    cwe_id: str | None = None
    owasp_category: str | None = None
    exploitability: ExploitabilityScore = field(default_factory=ExploitabilityScore)
    source: str = ""
    sink: str = ""
    missing_guard: str = ""
    evidence_path: list[EvidencePathStep | dict[str, str]] = field(default_factory=list)
    attack_scenario: str = ""
    impact: str = ""
    fix: str = ""
    false_positive_reason: str = ""
    uncertainty: str = ""
    provider: str = ""
    model: str = ""
    raw_model_output: str = ""

    def __post_init__(self) -> None:
        self.verdict = Verdict.parse(self.verdict)
        self.severity = Severity.parse(self.severity)
        self.confidence = Confidence.parse(self.confidence)
        self.evidence_path = [self._parse_step(step) for step in self.evidence_path]
        self._validate_required()
        self._apply_quality_gate()

    @staticmethod
    def _parse_step(step: EvidencePathStep | dict[str, str]) -> EvidencePathStep:
        if isinstance(step, EvidencePathStep):
            return step
        return EvidencePathStep(
            location=step.get("location", ""),
            evidence=step.get("evidence", ""),
            kind=step.get("kind", "code"),
        )

    def _validate_required(self) -> None:
        if not self.id.strip():
            raise ValueError("Finding id is required")
        if not self.title.strip():
            raise ValueError("Finding title is required")
        if self.start_line is not None and self.start_line < 1:
            raise ValueError("start_line must be positive")
        if (
            self.end_line is not None
            and self.start_line is not None
            and self.end_line < self.start_line
        ):
            raise ValueError("end_line cannot be before start_line")

    def _apply_quality_gate(self) -> None:
        if (not self.file_path or self.start_line is None) and self.confidence == Confidence.HIGH:
            self.confidence = Confidence.MEDIUM

        if self.verdict == Verdict.EXPLOITABLE and not self.evidence_path:
            self.verdict = Verdict.UNCERTAIN
            self.confidence = Confidence.LOW
            self.uncertainty = self._append_reason(
                self.uncertainty,
                "No evidence path was provided.",
            )

        missing_core = not (self.source and self.sink and self.missing_guard)
        if self.verdict in SERIOUS_VERDICTS and missing_core:
            if self.confidence == Confidence.HIGH:
                self.confidence = Confidence.MEDIUM
            self.uncertainty = self._append_reason(
                self.uncertainty,
                "Source, sink, or missing guard evidence is incomplete.",
            )

        if self.false_positive_reason and self.verdict in SERIOUS_VERDICTS:
            self.verdict = Verdict.PROBABLY_FALSE_POSITIVE
            self.confidence = Confidence.MEDIUM

    @staticmethod
    def _append_reason(current: str, reason: str) -> str:
        if not current:
            return reason
        if reason in current:
            return current
        return f"{current} {reason}"

    @property
    def location(self) -> str:
        if not self.start_line:
            return self.file_path
        if self.end_line and self.end_line != self.start_line:
            return f"{self.file_path}:{self.start_line}-{self.end_line}"
        return f"{self.file_path}:{self.start_line}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "verdict": self.verdict.value,
            "severity": self.severity.value,
            "confidence": self.confidence.value,
            "exploitability_score": self.exploitability.to_dict(),
            "cwe_id": self.cwe_id,
            "owasp_category": self.owasp_category,
            "file_path": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "source": self.source,
            "sink": self.sink,
            "missing_guard": self.missing_guard,
            "evidence_path": [step.to_dict() for step in self.evidence_path],
            "attack_scenario": self.attack_scenario,
            "impact": self.impact,
            "fix": self.fix,
            "false_positive_reason": self.false_positive_reason,
            "uncertainty": self.uncertainty,
            "provider": self.provider,
            "model": self.model,
            "raw_model_output": self.raw_model_output,
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)
