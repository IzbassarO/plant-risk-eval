"""Hardened second-review evidence validation (R2B.2 Part 4).

G07/G08/G10 are conservatively excluded from Core Dataset V1, so this validator
no longer gates the Core dataset. It still gates the Risk Evaluation Layer, and
the audit found gaps worth closing before it is relied on there:

* reviewer independence compared raw strings, so ``HUMAN_REVIEWER_1`` was
  treated as a different person from ``human_reviewer_1``;
* placeholder detection matched whole strings only, so ``TBD.`` and
  ``source to be supplied`` passed while a bare ``TBD`` did not;
* a reviewer qualification of ``x`` was acceptable;
* nothing required a rationale to be about the group it was filed under, and
  nothing noticed the same rationale or citation set pasted into all three.

None of this can decide scientific truth, and none of it tries to. It refuses
input that carries no evidence, which is a different and much smaller claim.
"""
from __future__ import annotations

import csv
import subprocess
from pathlib import Path

import pytest

from ica26.governance.approvals import SECOND_REVIEW_SPEC, validate_approval
from ica26.governance.second_review import (
    MIN_REVIEWER_QUALIFICATION_CHARS,
    MIN_SHARED_EVIDENCE_BASIS_CHARS,
    _is_review_placeholder,
)

from test_governance_approvals import (  # noqa: E402 - shared fixtures
    _group,
    _second_review_payload,
    second_review_repo,
)

__all__ = ["second_review_repo"]


def _validate(repo, payload):
    return validate_approval(payload, SECOND_REVIEW_SPEC, repo=repo,
                             path="second_review.json")


def _violations(repo, payload) -> str:
    return " ".join(_validate(repo, payload).violations)


# --------------------------------------------------------------------------- #
# The baseline must stay satisfiable
# --------------------------------------------------------------------------- #
def test_a_genuinely_complete_review_is_still_accepted(second_review_repo):
    """Hardening that rejects good input is just a broken validator."""
    verdict = _validate(second_review_repo, _second_review_payload(second_review_repo))
    assert verdict.valid, verdict.violations
    assert verdict.satisfied


# --------------------------------------------------------------------------- #
# Reviewer independence survives spelling
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("spelling", [
    "human_reviewer_1",
    "HUMAN_REVIEWER_1",
    "Human_Reviewer_1",
    "  human_reviewer_1  ",
    "ｈｕｍａｎ＿ｒｅｖｉｅｗｅｒ＿１",     # full-width, NFKC-equivalent
])
def test_the_first_reviewer_cannot_second_review_under_any_spelling(
    second_review_repo, spelling,
):
    payload = _second_review_payload(second_review_repo)
    _group(payload, "G07")["reviewer_id"] = spelling
    assert "must be independent" in _violations(second_review_repo, payload)


def test_an_actually_different_reviewer_is_accepted(second_review_repo):
    payload = _second_review_payload(second_review_repo)
    _group(payload, "G07")["reviewer_id"] = "human_reviewer_2"
    assert _validate(second_review_repo, payload).valid


# --------------------------------------------------------------------------- #
# Placeholders hiding inside real sentences
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("value", [
    "TBD",
    "tbd.",
    "  TBD  ",
    "Source TBD",
    "citation: unknown",
    "pending review by the pathology group",
    "source to be supplied once the herbarium responds",
    "diagnosis unknown at this time",
    "placeholder until a real citation exists",
    "n/a",
    "value is N/A for this group",
])
def test_embedded_placeholder_tokens_are_detected(value):
    assert _is_review_placeholder(value) is True


@pytest.mark.parametrize("value", [
    "Agrios, Plant Pathology, 5th edition, chapter 11",
    "The latest survey of Alternaria solani lesions on Solanum tuberosum",
    "Compendium of Tomato Diseases, APS Press, page 24",
    # 'latest' contains 'test'; a naive substring rule would reject this.
    "Confirmed against the latest APS compendium entry",
])
def test_real_prose_is_not_mistaken_for_a_placeholder(value):
    assert _is_review_placeholder(value) is False


def test_a_rationale_padded_around_a_placeholder_is_refused(second_review_repo):
    payload = _second_review_payload(second_review_repo)
    _group(payload, "G08")["diagnostic_rationale"] = (
        "For G08 the supporting diagnostic source is TBD, but the label looks "
        "plausible enough to keep for now.")
    assert "diagnostic_rationale" in _violations(second_review_repo, payload)


def test_a_placeholder_citation_inside_longer_text_is_refused(second_review_repo):
    payload = _second_review_payload(second_review_repo)
    _group(payload, "G08")["diagnostic_citations"] = [{
        "citation": "Authoritative source to be supplied",
        "url": "https://example.org/diagnostics/g08",
    }]
    assert "citation" in _violations(second_review_repo, payload)


# --------------------------------------------------------------------------- #
# Reviewer qualification
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("qualification", ["x", "expert", "PhD", "a b"])
def test_a_meaningless_qualification_is_refused(second_review_repo, qualification):
    payload = _second_review_payload(second_review_repo)
    _group(payload, "G07")["reviewer_role_or_qualification"] = qualification
    assert "reviewer_role_or_qualification" in _violations(second_review_repo, payload)


@pytest.mark.parametrize("qualification", [
    "plant pathology reviewer",
    "extension plant pathologist, potato and tomato diseases",
])
def test_a_real_qualification_is_accepted(second_review_repo, qualification):
    payload = _second_review_payload(second_review_repo)
    for group in ("G07", "G08", "G10"):
        _group(payload, group)["reviewer_role_or_qualification"] = qualification
    assert _validate(second_review_repo, payload).valid
    assert len(qualification) >= MIN_REVIEWER_QUALIFICATION_CHARS


# --------------------------------------------------------------------------- #
# Rationale must be about its own group
# --------------------------------------------------------------------------- #
def test_a_generic_rationale_that_names_no_group_is_refused(second_review_repo):
    payload = _second_review_payload(second_review_repo)
    _group(payload, "G07")["diagnostic_rationale"] = (
        "The current canonical label is consistent with the cited literature and "
        "the visible symptoms on the leaf surface.")
    assert "does not identify G07" in _violations(second_review_repo, payload)


def test_one_group_may_not_borrow_another_groups_reasoning(second_review_repo):
    payload = _second_review_payload(second_review_repo)
    _group(payload, "G07")["diagnostic_rationale"] = (
        "For G07 this follows the same reasoning already given for G10, which "
        "settles the matter for both of them.")
    violations = _violations(second_review_repo, payload)
    assert "borrow another group's reasoning" in violations


def test_a_citation_filed_under_the_wrong_group_is_refused(second_review_repo):
    payload = _second_review_payload(second_review_repo)
    _group(payload, "G07")["diagnostic_citations"] = [{
        "citation": "Diagnostic source establishing the G08 tomato lesion",
        "url": "https://example.org/diagnostics/g07",
    }]
    assert "must be evidence about G07" in _violations(second_review_repo, payload)


# --------------------------------------------------------------------------- #
# Copy-paste across the three groups
# --------------------------------------------------------------------------- #
def test_an_identical_rationale_across_groups_is_refused(second_review_repo):
    payload = _second_review_payload(second_review_repo)
    shared = ("Each reviewed group carries a canonical label consistent with the "
              "cited diagnostic reference for G07 G08 G10 alike.")
    for group in ("G07", "G08", "G10"):
        _group(payload, group)["diagnostic_rationale"] = shared
    assert "share an identical diagnostic_rationale" in _violations(
        second_review_repo, payload)


def test_an_identical_citation_set_across_groups_needs_a_declaration(
    second_review_repo,
):
    payload = _second_review_payload(second_review_repo)
    shared = [{"citation": "Compendium of Solanaceous Crop Diseases, APS Press",
               "url": "https://example.org/diagnostics/compendium"}]
    for group in ("G07", "G08", "G10"):
        _group(payload, group)["diagnostic_citations"] = shared
    violations = _violations(second_review_repo, payload)
    assert "without declaring shared_evidence_basis" in violations


def test_a_declared_shared_source_with_group_specific_reasoning_is_accepted(
    second_review_repo,
):
    """One source may genuinely cover three groups -- if the reviewer says so."""
    payload = _second_review_payload(second_review_repo)
    shared = [{"citation": "Compendium of Solanaceous Crop Diseases, APS Press",
               "url": "https://example.org/diagnostics/compendium"}]
    for group in ("G07", "G08", "G10"):
        entry = _group(payload, group)
        entry["diagnostic_citations"] = shared
        entry["shared_evidence_basis"] = (
            "One compendium covers all three Solanaceae groups; each group is "
            "assessed separately against its own plate in that reference.")
        entry["diagnostic_rationale"] = (
            f"For {group} the lesion morphology matches the compendium plate "
            f"cited for its crop, supporting the current canonical label.")
    verdict = _validate(second_review_repo, payload)
    assert verdict.valid, verdict.violations


def test_a_declared_shared_basis_may_not_itself_be_a_placeholder(second_review_repo):
    payload = _second_review_payload(second_review_repo)
    for group in ("G07", "G08", "G10"):
        _group(payload, group)["shared_evidence_basis"] = "TBD"
    violations = _violations(second_review_repo, payload)
    assert "shared_evidence_basis" in violations
    assert MIN_SHARED_EVIDENCE_BASIS_CHARS > 0


def test_a_shared_basis_does_not_excuse_identical_reasoning(second_review_repo):
    """Declaring a shared source is not permission to paste one rationale."""
    payload = _second_review_payload(second_review_repo)
    shared_rationale = ("The cited compendium supports the canonical labels for "
                        "G07 G08 G10 without further qualification here.")
    for group in ("G07", "G08", "G10"):
        entry = _group(payload, group)
        entry["shared_evidence_basis"] = (
            "One compendium covers all three Solanaceae groups; each group is "
            "assessed separately against its own plate in that reference.")
        entry["diagnostic_rationale"] = shared_rationale
    assert "share an identical diagnostic_rationale" in _violations(
        second_review_repo, payload)


# --------------------------------------------------------------------------- #
# The exclusion artifact must not masquerade as a scientific review
# --------------------------------------------------------------------------- #
def test_the_conservative_exclusion_is_not_a_second_review(repo_root):
    """Part 1's operator decision must not satisfy this validator's contract."""
    decision = Path("data/exclusions/core_dataset_v1_conservative_exclusions.csv")
    with (repo_root / decision).open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert rows
    for row in rows:
        # It carries no verdict on the diagnosis, no citation, and no confidence.
        assert "decision" not in {k for k in row if k.endswith("decision")} - {
            "exclusion_decision", "prior_remediation_action"}
        assert not any(k.startswith("diagnostic") for k in row)
        assert row["exclusion_decision"] == "conservative_exclusion"
        assert row["reviewer_role"] == "dataset_owner_research_lead"


def test_the_scientific_second_review_is_still_reported_as_not_performed(repo_root):
    artifact = repo_root / "human_review/plantdoc_label_second_review/second_review.json"
    assert not artifact.exists()


def test_no_code_path_can_fabricate_a_second_review(repo_root):
    """No shipped code may WRITE the artifact this validator exists to check.

    Naming the path in order to validate it is exactly right; naming it next to
    a write call is not. The distinction is what keeps "the review has not been
    performed" an honest statement rather than one line of code away from false.
    """
    target = "second_review.json"
    writers = ("write_text(", "open(", "to_csv(", "json.dump(", "atomic_write")
    for source in sorted((repo_root / "src").rglob("*.py")) + sorted(
            (repo_root / "scripts").rglob("*.py")):
        text = source.read_text(encoding="utf-8")
        if target not in text:
            continue
        for line in text.splitlines():
            if target in line and any(w in line for w in writers):
                raise AssertionError(
                    f"{source.relative_to(repo_root)} appears to write {target}: "
                    f"{line.strip()}")
