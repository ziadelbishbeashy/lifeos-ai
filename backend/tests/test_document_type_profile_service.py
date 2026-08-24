"""Tests for centralized Document Brain type profiles."""

from services.document_analysis_service import (
    normalise_document_type,
)
from services.document_type_profile_service import (
    AUTO_DETECT_TYPE_KEY,
    DOCUMENT_TYPE_PROFILES,
    build_detection_catalog,
    build_profile_section_catalog,
    document_type_choices,
    get_document_type_label,
    get_document_type_profile,
    normalise_document_type_key,
    resolve_document_type_key,
    supported_document_type_keys,
    supported_document_type_labels,
)


def test_supported_profiles_have_unique_keys_and_labels():
    keys = [
        profile.key
        for profile in DOCUMENT_TYPE_PROFILES
    ]

    labels = [
        profile.label
        for profile in DOCUMENT_TYPE_PROFILES
    ]

    assert len(keys) == len(
        set(keys)
    )
    assert len(labels) == len(
        set(labels)
    )


def test_expected_document_types_are_supported():
    assert supported_document_type_labels() == (
        "Requirements Document",
        "Research Paper",
        "Meeting Notes",
        "Project Plan",
        "Technical Documentation",
        "Lecture Material",
        "Policy",
        "Contract",
        "General Reference",
    )


def test_aliases_normalise_to_canonical_keys():
    assert normalise_document_type_key(
        "SRS"
    ) == "requirements_document"

    assert normalise_document_type_key(
        "conference paper"
    ) == "research_paper"

    assert normalise_document_type_key(
        "meeting minutes"
    ) == "meeting_notes"

    assert normalise_document_type_key(
        "service agreement"
    ) == "contract"


def test_unknown_type_falls_back_safely():
    assert normalise_document_type_key(
        "mystery file"
    ) == "general_reference"

    assert get_document_type_label(
        "mystery file"
    ) == "General Reference"


def test_auto_is_only_allowed_when_requested():
    assert normalise_document_type_key(
        "auto"
    ) == "general_reference"

    assert normalise_document_type_key(
        "auto",
        allow_auto=True,
    ) == AUTO_DETECT_TYPE_KEY


def test_form_choices_can_include_automatic_detection():
    choices = document_type_choices(
        include_auto=True
    )

    assert choices[0] == (
        "auto",
        "Detect automatically",
    )

    assert (
        "research_paper",
        "Research Paper",
    ) in choices


def test_research_profile_exposes_specialized_sections():
    profile = get_document_type_profile(
        "Research Paper"
    )

    section_keys = {
        section.key
        for section in profile.sections
    }

    assert "research_problem" in section_keys
    assert "methodology" in section_keys
    assert "findings" in section_keys
    assert "limitations" in section_keys
    assert "research_gaps" in section_keys


def test_policy_and_contract_are_separate_profiles():
    assert get_document_type_profile(
        "Policy"
    ).key == "policy"

    assert get_document_type_profile(
        "Contract"
    ).key == "contract"

    assert get_document_type_profile(
        "Policy"
    ).sections != get_document_type_profile(
        "Contract"
    ).sections


def test_step5_normaliser_uses_central_profiles():
    assert normalise_document_type(
        "academic paper"
    ) == "Research Paper"

    assert normalise_document_type(
        "Meeting Notes"
    ) == "Meeting Notes"

    assert normalise_document_type(
        "unknown"
    ) == "General Reference"


def test_prompt_catalogs_are_generated_from_profiles():
    detection_catalog = build_detection_catalog()

    assert "Research Paper" in detection_catalog
    assert "Meeting Notes" in detection_catalog
    assert "Contract" in detection_catalog

    research_catalog = build_profile_section_catalog(
        "research_paper"
    )

    assert "research_problem" in research_catalog
    assert "methodology" in research_catalog
    assert "limitations" in research_catalog


def test_all_profiles_have_at_least_one_section():
    assert all(
        profile.sections
        for profile in DOCUMENT_TYPE_PROFILES
    )


def test_supported_keys_match_profile_order():
    assert supported_document_type_keys() == tuple(
        profile.key
        for profile in DOCUMENT_TYPE_PROFILES
    )



def test_strict_type_resolution_does_not_guess():
    assert resolve_document_type_key(
        "research_paper"
    ) == "research_paper"

    assert resolve_document_type_key(
        "conference paper"
    ) == "research_paper"

    assert resolve_document_type_key(
        "financial_report"
    ) is None
