"""Central document-type definitions for Document Brain Step 6."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


AUTO_DETECT_TYPE_KEY = "auto"
GENERAL_REFERENCE_TYPE_KEY = "general_reference"


@dataclass(frozen=True)
class DocumentTypeSection:
    """One type-specific analysis section."""

    key: str
    label: str
    description: str
    value_kind: str = "items"


@dataclass(frozen=True)
class DocumentTypeProfile:
    """Configuration for one supported document type."""

    key: str
    label: str
    description: str
    detection_guidance: str
    sections: tuple[DocumentTypeSection, ...]
    aliases: tuple[str, ...] = ()


def _section(
    key: str,
    label: str,
    description: str,
    *,
    value_kind: str = "items",
) -> DocumentTypeSection:
    return DocumentTypeSection(
        key=key,
        label=label,
        description=description,
        value_kind=value_kind,
    )


DOCUMENT_TYPE_PROFILES: tuple[DocumentTypeProfile, ...] = (
    DocumentTypeProfile(
        key="requirements_document",
        label="Requirements Document",
        description=(
            "Requirements, specifications, constraints, acceptance "
            "criteria, or system/business needs."
        ),
        detection_guidance=(
            "Use when the document primarily defines what a system, "
            "product, process, or project must do or satisfy."
        ),
        sections=(
            _section(
                "scope",
                "Scope",
                "What is included and excluded.",
                value_kind="text",
            ),
            _section(
                "functional_requirements",
                "Functional Requirements",
                "Required functions or behaviours.",
            ),
            _section(
                "non_functional_requirements",
                "Non-functional Requirements",
                "Quality, performance, security, usability, or other constraints.",
            ),
            _section(
                "constraints",
                "Constraints",
                "Technical, business, legal, schedule, or resource limitations.",
            ),
            _section(
                "acceptance_criteria",
                "Acceptance Criteria",
                "Conditions used to decide whether requirements are satisfied.",
            ),
            _section(
                "dependencies",
                "Dependencies",
                "External systems, teams, services, or prerequisites.",
            ),
            _section(
                "priorities",
                "Priorities",
                "Explicit requirement priorities or ordering.",
            ),
        ),
        aliases=(
            "requirements",
            "specification",
            "requirements specification",
            "software requirements specification",
            "srs",
        ),
    ),
    DocumentTypeProfile(
        key="research_paper",
        label="Research Paper",
        description=(
            "Academic or scientific work presenting a research problem, "
            "method, results, and conclusions."
        ),
        detection_guidance=(
            "Use when the document reports or reviews research and commonly "
            "contains methodology, experiments, results, limitations, or citations."
        ),
        sections=(
            _section(
                "research_problem",
                "Research Problem",
                "The problem, gap, or research question being addressed.",
                value_kind="text",
            ),
            _section(
                "objectives",
                "Objectives",
                "Research aims, hypotheses, or goals.",
            ),
            _section(
                "methodology",
                "Methodology",
                "Methods, experimental design, models, or procedures.",
            ),
            _section(
                "dataset_or_participants",
                "Dataset or Participants",
                "Datasets, samples, participants, or evaluated material.",
            ),
            _section(
                "findings",
                "Findings",
                "Main results and supported conclusions.",
            ),
            _section(
                "limitations",
                "Limitations",
                "Limitations explicitly acknowledged by the paper.",
            ),
            _section(
                "research_gaps",
                "Research Gaps",
                "Open gaps explicitly identified or supported by the paper.",
            ),
            _section(
                "future_work",
                "Future Work",
                "Future directions proposed by the authors.",
            ),
        ),
        aliases=(
            "paper",
            "academic paper",
            "scientific paper",
            "journal article",
            "conference paper",
            "research article",
        ),
    ),
    DocumentTypeProfile(
        key="meeting_notes",
        label="Meeting Notes",
        description=(
            "Meeting minutes, discussion notes, decisions, owners, and follow-up work."
        ),
        detection_guidance=(
            "Use when the document records a meeting, discussion, attendees, "
            "decisions, assigned actions, or follow-up dates."
        ),
        sections=(
            _section(
                "meeting_date",
                "Meeting Date",
                "The meeting date when explicitly stated.",
                value_kind="text",
            ),
            _section(
                "participants",
                "Participants",
                "People or roles attending the meeting.",
            ),
            _section(
                "agenda",
                "Agenda",
                "Planned meeting topics.",
            ),
            _section(
                "discussion_topics",
                "Discussion Topics",
                "Main topics discussed.",
            ),
            _section(
                "decisions",
                "Decisions",
                "Decisions agreed during the meeting.",
            ),
            _section(
                "action_owners",
                "Action Owners",
                "Actions together with explicitly assigned owners.",
            ),
            _section(
                "deadlines",
                "Deadlines",
                "Dates attached to decisions or actions.",
            ),
            _section(
                "unresolved_topics",
                "Unresolved Topics",
                "Issues left open or needing follow-up.",
            ),
            _section(
                "next_meeting",
                "Next Meeting",
                "Next meeting details when explicitly stated.",
                value_kind="text",
            ),
        ),
        aliases=(
            "meeting",
            "meeting minutes",
            "minutes",
            "meeting summary",
        ),
    ),
    DocumentTypeProfile(
        key="project_plan",
        label="Project Plan",
        description=(
            "Plans describing objectives, scope, deliverables, milestones, "
            "resources, dependencies, and timelines."
        ),
        detection_guidance=(
            "Use when the document primarily plans how a project will be "
            "executed, scheduled, resourced, or measured."
        ),
        sections=(
            _section(
                "objectives",
                "Objectives",
                "Project goals and intended outcomes.",
            ),
            _section(
                "scope",
                "Scope",
                "Included and excluded project work.",
                value_kind="text",
            ),
            _section(
                "deliverables",
                "Deliverables",
                "Expected outputs or completed work products.",
            ),
            _section(
                "milestones",
                "Milestones",
                "Important project checkpoints.",
            ),
            _section(
                "dependencies",
                "Dependencies",
                "Prerequisites and external dependencies.",
            ),
            _section(
                "resources",
                "Resources",
                "People, systems, budget, or other planned resources.",
            ),
            _section(
                "timeline",
                "Timeline",
                "Schedule information and sequencing.",
            ),
            _section(
                "risks",
                "Risks",
                "Project risks explicitly stated in the plan.",
            ),
            _section(
                "success_criteria",
                "Success Criteria",
                "How project success will be evaluated.",
            ),
        ),
        aliases=(
            "plan",
            "project roadmap",
            "implementation plan",
            "delivery plan",
        ),
    ),
    DocumentTypeProfile(
        key="technical_documentation",
        label="Technical Documentation",
        description=(
            "Technical reference, architecture, API, setup, configuration, "
            "usage, or troubleshooting documentation."
        ),
        detection_guidance=(
            "Use when the document mainly explains how a technical system, "
            "component, API, integration, or tool works or is used."
        ),
        sections=(
            _section(
                "system_overview",
                "System Overview",
                "What the technical system or component does.",
                value_kind="text",
            ),
            _section(
                "components",
                "Components",
                "Major modules, services, or technical components.",
            ),
            _section(
                "setup_steps",
                "Setup Steps",
                "Installation or initialization instructions.",
            ),
            _section(
                "configuration",
                "Configuration",
                "Configuration options and required settings.",
            ),
            _section(
                "dependencies",
                "Dependencies",
                "Libraries, systems, services, or environmental dependencies.",
            ),
            _section(
                "interfaces_or_apis",
                "Interfaces or APIs",
                "Interfaces, endpoints, protocols, or integration boundaries.",
            ),
            _section(
                "usage_instructions",
                "Usage Instructions",
                "How users or developers use the system.",
            ),
            _section(
                "troubleshooting",
                "Troubleshooting",
                "Known errors, failure cases, and recovery guidance.",
            ),
        ),
        aliases=(
            "technical docs",
            "technical document",
            "documentation",
            "developer documentation",
            "api documentation",
            "architecture document",
        ),
    ),
    DocumentTypeProfile(
        key="lecture_material",
        label="Lecture Material",
        description=(
            "Teaching material such as lecture notes, course handouts, "
            "study material, or lesson slides converted to PDF."
        ),
        detection_guidance=(
            "Use when the document is designed primarily to teach or explain "
            "course concepts rather than report research or define a project."
        ),
        sections=(
            _section(
                "learning_objectives",
                "Learning Objectives",
                "Explicit learning goals.",
            ),
            _section(
                "main_concepts",
                "Main Concepts",
                "Core ideas the learner should understand.",
            ),
            _section(
                "definitions",
                "Definitions",
                "Important terms and definitions.",
            ),
            _section(
                "examples",
                "Examples",
                "Worked or explanatory examples.",
            ),
            _section(
                "formulas",
                "Formulas",
                "Equations or formulas and their meanings.",
            ),
            _section(
                "processes",
                "Processes",
                "Step-by-step methods or procedures.",
            ),
            _section(
                "comparisons",
                "Important Comparisons",
                "Concepts the material explicitly compares.",
            ),
            _section(
                "revision_questions",
                "Revision Questions",
                "Useful study questions grounded in the material.",
            ),
        ),
        aliases=(
            "lecture",
            "lecture notes",
            "course material",
            "study material",
            "lesson notes",
            "class notes",
        ),
    ),
    DocumentTypeProfile(
        key="policy",
        label="Policy",
        description=(
            "Formal policy defining rules, responsibilities, scope, "
            "exceptions, compliance, or consequences."
        ),
        detection_guidance=(
            "Use when the document establishes organisational rules, "
            "standards, responsibilities, compliance expectations, or exceptions."
        ),
        sections=(
            _section(
                "policy_purpose",
                "Policy Purpose",
                "Why the policy exists.",
                value_kind="text",
            ),
            _section(
                "scope",
                "Scope",
                "Who and what the policy applies to.",
                value_kind="text",
            ),
            _section(
                "rules",
                "Rules",
                "Rules or required behaviours.",
            ),
            _section(
                "responsibilities",
                "Responsibilities",
                "Roles and responsibilities established by the policy.",
            ),
            _section(
                "exceptions",
                "Exceptions",
                "Explicit exceptions or exemption conditions.",
            ),
            _section(
                "compliance_requirements",
                "Compliance Requirements",
                "Required controls, reporting, or compliance activities.",
            ),
            _section(
                "effective_dates",
                "Effective Dates",
                "Effective, review, expiry, or revision dates.",
            ),
            _section(
                "consequences",
                "Consequences",
                "Consequences of non-compliance when explicitly stated.",
            ),
        ),
        aliases=(
            "policy document",
            "company policy",
            "procedure policy",
        ),
    ),
    DocumentTypeProfile(
        key="contract",
        label="Contract",
        description=(
            "Agreement defining parties, obligations, payment terms, "
            "important dates, termination, liabilities, or dispute terms."
        ),
        detection_guidance=(
            "Use when the document is an agreement between parties and "
            "contains contractual obligations, rights, payments, or legal terms."
        ),
        sections=(
            _section(
                "parties",
                "Parties",
                "Named contracting parties.",
            ),
            _section(
                "obligations",
                "Obligations",
                "Duties and commitments of the parties.",
            ),
            _section(
                "payment_terms",
                "Payment Terms",
                "Payment amounts, timing, or conditions.",
            ),
            _section(
                "important_dates",
                "Important Dates",
                "Start, renewal, delivery, payment, or expiry dates.",
            ),
            _section(
                "termination_conditions",
                "Termination Conditions",
                "How and when the agreement may end.",
            ),
            _section(
                "liabilities",
                "Liabilities",
                "Liability, indemnity, or responsibility clauses.",
            ),
            _section(
                "confidentiality",
                "Confidentiality",
                "Confidentiality or information-handling obligations.",
            ),
            _section(
                "dispute_terms",
                "Dispute Terms",
                "Dispute resolution or governing-law terms.",
            ),
            _section(
                "contract_risks",
                "Contract Risks",
                "Explicit obligations or clauses that may require attention.",
            ),
        ),
        aliases=(
            "agreement",
            "legal agreement",
            "service agreement",
            "contract document",
        ),
    ),
    DocumentTypeProfile(
        key=GENERAL_REFERENCE_TYPE_KEY,
        label="General Reference",
        description=(
            "A general document that does not clearly match one specialized type."
        ),
        detection_guidance=(
            "Use only when no other supported type clearly describes the "
            "document's primary purpose."
        ),
        sections=(
            _section(
                "topics",
                "Main Topics",
                "Main subjects covered by the document.",
            ),
            _section(
                "key_facts",
                "Key Facts",
                "Important factual information.",
            ),
            _section(
                "important_details",
                "Important Details",
                "Details useful for understanding or using the document.",
            ),
        ),
        aliases=(
            "general",
            "reference",
            "other",
            "generic",
        ),
    ),
)


_PROFILE_BY_KEY = {
    profile.key: profile
    for profile in DOCUMENT_TYPE_PROFILES
}

_PROFILE_BY_LABEL = {
    profile.label.casefold(): profile
    for profile in DOCUMENT_TYPE_PROFILES
}

_PROFILE_BY_ALIAS = {
    alias.casefold(): profile
    for profile in DOCUMENT_TYPE_PROFILES
    for alias in profile.aliases
}


def supported_document_type_keys() -> tuple[str, ...]:
    """Return canonical type keys in UI display order."""

    return tuple(
        profile.key
        for profile in DOCUMENT_TYPE_PROFILES
    )


def supported_document_type_labels() -> tuple[str, ...]:
    """Return user-facing labels in UI display order."""

    return tuple(
        profile.label
        for profile in DOCUMENT_TYPE_PROFILES
    )


def document_type_choices(
    *,
    include_auto: bool = False,
) -> tuple[tuple[str, str], ...]:
    """Return safe values and labels for forms/select controls."""

    choices = [
        (
            profile.key,
            profile.label,
        )
        for profile in DOCUMENT_TYPE_PROFILES
    ]

    if include_auto:
        choices.insert(
            0,
            (
                AUTO_DETECT_TYPE_KEY,
                "Detect automatically",
            ),
        )

    return tuple(
        choices
    )


def resolve_document_type_key(
    value: object,
    *,
    allow_auto: bool = False,
) -> str | None:
    """
    Resolve a supported key, label, or alias without guessing.

    Detection uses this strict helper so an unexpected AI value is
    rejected rather than silently converted to General Reference.
    """

    cleaned = " ".join(
        str(value or "").split()
    ).casefold()

    if allow_auto and cleaned in {
        AUTO_DETECT_TYPE_KEY,
        "automatic",
        "detect automatically",
        "auto detect",
        "auto-detect",
    }:
        return AUTO_DETECT_TYPE_KEY

    if cleaned in _PROFILE_BY_KEY:
        return cleaned

    label_match = _PROFILE_BY_LABEL.get(
        cleaned
    )

    if label_match is not None:
        return label_match.key

    alias_match = _PROFILE_BY_ALIAS.get(
        cleaned
    )

    if alias_match is not None:
        return alias_match.key

    return None


def normalise_document_type_key(
    value: object,
    *,
    allow_auto: bool = False,
) -> str:
    """
    Convert a key, label, or known alias to a canonical type key.

    Unknown values retain Step 5 compatibility by falling back to
    General Reference. Automatic detection is accepted only when
    explicitly requested.
    """

    resolved = resolve_document_type_key(
        value,
        allow_auto=allow_auto,
    )

    if resolved is not None:
        return resolved

    # Step 5 compatibility: this used to be one combined type.
    cleaned = " ".join(
        str(value or "").split()
    ).casefold()

    if cleaned == "policy or contract":
        return GENERAL_REFERENCE_TYPE_KEY

    return GENERAL_REFERENCE_TYPE_KEY


def get_document_type_profile(
    value: object,
) -> DocumentTypeProfile:
    """Return a profile for a key, label, or alias."""

    key = normalise_document_type_key(
        value
    )

    return _PROFILE_BY_KEY[
        key
    ]


def get_document_type_label(
    value: object,
) -> str:
    """Return the canonical user-facing label."""

    return get_document_type_profile(
        value
    ).label


def find_profile_by_exact_label(
    value: object,
) -> DocumentTypeProfile | None:
    """Return a profile only when the supplied label is supported."""

    cleaned = " ".join(
        str(value or "").split()
    ).casefold()

    return _PROFILE_BY_LABEL.get(
        cleaned
    )


def build_detection_catalog() -> str:
    """Return concise type guidance for the future classifier prompt."""

    lines: list[str] = []

    for profile in DOCUMENT_TYPE_PROFILES:
        lines.append(
            f"- {profile.label}: {profile.detection_guidance}"
        )

    return "\n".join(
        lines
    )


def build_profile_section_catalog(
    value: object,
) -> str:
    """Return type-specific section guidance for the analysis prompt."""

    profile = get_document_type_profile(
        value
    )

    return "\n".join(
        (
            f"- {section.key} ({section.label}): "
            f"{section.description}"
        )
        for section in profile.sections
    )
