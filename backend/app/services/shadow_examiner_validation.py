"""Shadow OET Examiner -- offline schema-validation harness (Phase 2).

Validates model-shaped JSON text against the Phase 1 schema
(``app.services.shadow_examiner``) before any of it would ever be trusted.
Pure: no model call, no ``ai_registry``, no database, no network access, no
change to ``score_speaking`` / ``/speaking/score`` / the Learning Brain.

    raw model-shaped JSON text (one family's response)
        -> parse_family_response_json()      # tolerate fences / wrapper objects
        -> per-item field/type checks          # extra fields, provenance
        -> shadow_examiner.CriterionJudgement  # Phase 1 field/level/label rules
        -> shadow_examiner.validate_family_judgements()  # Phase 1 coverage rule
        -> ValidationResult

No partial trust (design doc, `shadow_examiner.validate_family_judgements`
docstring): a parse error, one bad criterion, a wrong family, an extra
field, or a bad evidence pointer invalidates the WHOLE family batch, never
just the offending entry. ``safe_fallback_judgements()`` then produces that
family's full criterion set at status=limited_evidence / level=None -- never
a real score, and never re-using raw model text as justification.
"""
from __future__ import annotations

import json
import re
from typing import List, Optional, Tuple

from pydantic import BaseModel

from app.services import shadow_examiner as se
from app.services.criterion_evidence import CriterionEvidenceMap
from app.services.examiner_input import CLINICAL_CRITERIA, LINGUISTIC_CRITERIA
from app.services.speaking_evidence import SOURCE_DETERMINISTIC, SOURCE_SEMANTIC

# ── Provenance vocabulary (matches shadow_examiner._EVIDENCE_HIERARCHY_RULES'
# own prompt text: "direct, deterministic_rule, semantic_model, or hybrid") ──
PROVENANCE_DIRECT = "direct"
PROVENANCE_HYBRID = "hybrid"
VALID_PROVENANCE = {PROVENANCE_DIRECT, SOURCE_DETERMINISTIC, SOURCE_SEMANTIC, PROVENANCE_HYBRID}

_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)

_ALLOWED_JUDGEMENT_FIELDS = set(se.CriterionJudgement.model_fields.keys())
_ALLOWED_EVIDENCE_FIELDS = set(se.EvidenceRefPointer.model_fields.keys())
_ALLOWED_TOP_LEVEL_KEYS = {"criteria"}

FALLBACK_JUSTIFICATION = (
    "Shadow examiner validation fallback: this family's response failed offline "
    "schema validation and was not trusted. See the ValidationResult.errors for "
    "the reason; the original model text is never surfaced here."
)
FALLBACK_LIMITATION = "family_validation_failed"


class ValidationResult(BaseModel):
    """Typed outcome of validating one family's model-shaped response."""

    valid: bool
    family: Optional[str] = None
    errors: List[str] = []
    judgements: Optional[List[se.CriterionJudgement]] = None
    safe_fallback_available: bool = False


def _strip_fence(raw: str) -> str:
    match = _FENCE_RE.match(raw.strip())
    return match.group(1) if match else raw


def parse_family_response_json(raw: Optional[str]) -> Tuple[Optional[list], Optional[str]]:
    """Parse model output text into a list of criterion-judgement dicts.

    Tolerates a bare JSON array (the documented contract --
    ``shadow_examiner._OUTPUT_SCHEMA_INSTRUCTIONS``), a fenced ```` ```json ...
    ``` ```` block, or an object wrapping the array as ``{"criteria": [...]}``
    (defensive: some models wrap arrays even when told not to). Any other
    top-level key on that wrapper object is rejected rather than silently
    dropped (STEP 12: no smuggled ``overall_band`` / ``combined_score``).

    Returns ``(items, None)`` on success or ``(None, error_message)`` on
    failure. Never raises.
    """
    if raw is None or not raw.strip():
        return None, "empty response"

    text = _strip_fence(raw)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"malformed JSON: {exc}"

    if isinstance(data, list):
        return data, None

    if isinstance(data, dict):
        extra_top_level = set(data.keys()) - _ALLOWED_TOP_LEVEL_KEYS
        if extra_top_level:
            return None, f"unsupported top-level field(s): {sorted(extra_top_level)}"
        if isinstance(data.get("criteria"), list):
            return data["criteria"], None
        return None, "'criteria' key must be a JSON array"

    return None, f"unexpected JSON shape: expected an array or {{'criteria': [...]}}, got {type(data).__name__}"


def _check_no_extra_fields(obj: dict, allowed: set, label: str, errors: List[str]) -> None:
    extra = set(obj.keys()) - allowed
    if extra:
        errors.append(f"{label}: unsupported field(s) {sorted(extra)}")


def _validate_item_structure(item: dict, errors: List[str]) -> None:
    label = str(item.get("criterion", "<unknown>"))
    _check_no_extra_fields(item, _ALLOWED_JUDGEMENT_FIELDS, label, errors)
    for ref in item.get("evidence_refs") or []:
        if not isinstance(ref, dict):
            errors.append(f"{label}: evidence_refs entry is not an object: {ref!r}")
            continue
        _check_no_extra_fields(ref, _ALLOWED_EVIDENCE_FIELDS, f"{label}.evidence_refs", errors)
        provenance = ref.get("provenance")
        if provenance is not None and provenance not in VALID_PROVENANCE:
            errors.append(f"{label}: invalid evidence provenance {provenance!r}")


def validate_family_response(family: str, raw: Optional[str]) -> ValidationResult:
    """Full offline pipeline for one family's model-shaped JSON response.

    Deterministic and side-effect free: the same ``(family, raw)`` input
    always returns an equal ``ValidationResult``. Makes no model call and no
    network call. Any single bad criterion invalidates the whole family (no
    partial trust) -- see module docstring.
    """
    if family not in se.VALID_FAMILIES:
        return ValidationResult(valid=False, family=family, errors=[f"invalid family: {family!r}"], safe_fallback_available=True)

    items, parse_error = parse_family_response_json(raw)
    if parse_error is not None:
        return ValidationResult(valid=False, family=family, errors=[parse_error], safe_fallback_available=True)

    errors: List[str] = []
    for item in items:
        if not isinstance(item, dict):
            errors.append(f"criterion entry is not an object: {item!r}")
            continue
        _validate_item_structure(item, errors)
    if errors:
        return ValidationResult(valid=False, family=family, errors=errors, safe_fallback_available=True)

    judgements: List[se.CriterionJudgement] = []
    for item in items:
        try:
            judgements.append(se.CriterionJudgement(**item))
        except Exception as exc:  # pydantic.ValidationError, or TypeError on a malformed item shape
            errors.append(str(exc))
    if errors:
        return ValidationResult(valid=False, family=family, errors=errors, safe_fallback_available=True)

    try:
        se.validate_family_judgements(family, judgements)
    except ValueError as exc:
        return ValidationResult(valid=False, family=family, errors=[str(exc)], safe_fallback_available=True)

    return ValidationResult(valid=True, family=family, errors=[], judgements=judgements, safe_fallback_available=False)


def _known_evidence_keys_by_criterion(family: str, criterion_evidence_map: CriterionEvidenceMap) -> dict:
    """criterion -> {(evidence_id, turn_index)} pulled from the map's own
    evidence_refs -- clinical bundles nest theirs under each indicator,
    linguistic bundles carry theirs directly on the bundle."""
    keys: dict = {}
    if family == se.FAMILY_CLINICAL:
        for bundle in criterion_evidence_map.clinical:
            refs = set()
            for indicator in bundle.indicators:
                refs.update((ref.evidence_id, ref.turn_index) for ref in indicator.evidence_refs)
            keys[bundle.criterion] = refs
    else:
        for bundle in criterion_evidence_map.linguistic:
            keys[bundle.criterion] = {(ref.evidence_id, ref.turn_index) for ref in bundle.evidence_refs}
    return keys


def validate_evidence_references(
    family: str, judgements: List[se.CriterionJudgement], criterion_evidence_map: CriterionEvidenceMap,
) -> List[str]:
    """Phase 3 addition (design doc's CRITICAL EVIDENCE AUDIT instruction):
    ``validate_family_response`` above only checks each EvidenceRefPointer's
    *shape* (valid evidence_level/provenance, no extra fields) -- it never
    checks whether (evidence_id, turn_index) actually exists in the
    CriterionEvidenceMap that was handed to the model, or whether it's cited
    under the RIGHT criterion. This closes that gap so a model can never get
    away with citing a fabricated evidence_id, a real evidence_id that
    belongs to a different criterion, or a turn_index that was never part of
    the evidence given to it.

    Returns one error string per bad citation (empty list = every citation
    in `judgements` is real and correctly attributed to its own criterion).
    Pure, no I/O, never raises -- callers decide what an error list means
    for trust (Phase 3's live harness treats any error here the same as a
    Phase 2 schema failure: whole-family safe fallback, no partial patch).
    """
    known = _known_evidence_keys_by_criterion(family, criterion_evidence_map)
    all_known_anywhere = set().union(*known.values()) if known else set()

    errors: List[str] = []
    for judgement in judgements:
        own = known.get(judgement.criterion, set())
        for ref in judgement.evidence_refs:
            key = (ref.evidence_id, ref.turn_index)
            if key in own:
                continue
            if key in all_known_anywhere:
                errors.append(
                    f"{judgement.criterion}: evidence_id={ref.evidence_id!r} turn_index={ref.turn_index!r} "
                    "exists in the CriterionEvidenceMap but under a different criterion"
                )
            else:
                errors.append(
                    f"{judgement.criterion}: evidence_id={ref.evidence_id!r} turn_index={ref.turn_index!r} "
                    "does not exist anywhere in the supplied CriterionEvidenceMap (fabricated)"
                )
    return errors


def safe_fallback_judgements(family: str) -> List[se.CriterionJudgement]:
    """STEP 10's safe conversion: a family validation failure becomes
    status=limited_evidence / level=None for every criterion in that family
    -- never a score of zero, and never a re-use of raw (untrusted) model
    text as justification. The reason belongs in ValidationResult.errors,
    not here.
    """
    if family not in se.VALID_FAMILIES:
        raise ValueError(f"invalid family: {family!r}")
    criteria = LINGUISTIC_CRITERIA if family == se.FAMILY_LINGUISTIC else CLINICAL_CRITERIA
    return [
        se.CriterionJudgement(
            criterion=criterion,
            family=family,
            status=se.STATUS_LIMITED_EVIDENCE,
            level=None,
            level_label=None,
            justification=FALLBACK_JUSTIFICATION,
            evidence_refs=[],
            evidence_quality=se.AVAILABILITY_INSUFFICIENT,
            limitations=[FALLBACK_LIMITATION],
        )
        for criterion in criteria
    ]
