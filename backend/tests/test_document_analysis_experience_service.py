"""Tests for the action-first Document Brain overview model."""

from types import SimpleNamespace

from services.document_analysis_experience_service import (
    build_document_analysis_experience,
)


def test_experience_prioritises_risks_gaps_actions_and_questions():
    overview = {
        "analysis": {
            "document_type": "Project Plan",
            "key_points": [
                {"title": "Launch readiness is the immediate goal", "detail": ""},
            ],
            "risks": [
                {
                    "risk": "Clean production database is not proven",
                    "impact": "Deployment may rely on undocumented objects.",
                    "source": {"page": 4, "evidence": "Prove a clean SQL Server database."},
                }
            ],
            "missing_information": [
                {
                    "question": "Who owns the final deployment?",
                    "why_it_matters": "Ownership affects launch readiness.",
                    "source": {"page": 5},
                }
            ],
            "deadlines": [
                {
                    "description": "Production launch",
                    "date": "2026-08-22",
                    "source": {"page": 1},
                }
            ],
            "questions": [
                {"question": "What could block launch?", "reason": ""},
            ],
            "action_items": [],
        }
    }

    workspace = {
        "type_key": "project_plan",
        "type_label": "Project Plan",
        "metadata": {
            "status_label": "Detected and confirmed",
            "confidence": "high",
        },
        "populated_sections": [
            {
                "key": "objectives",
                "label": "Objectives",
                "description": "Project goals.",
                "preview": "Launch safely",
                "count": 2,
                "items": [
                    {
                        "text": "Launch safely",
                        "detail": "",
                        "source": {"page": 1, "evidence": "Launch safely."},
                    }
                ],
            }
        ],
    }

    suggestions = [
        SimpleNamespace(
            status="Pending",
            title="Verify the clean database path",
            description="Create and migrate an empty production-like DB.",
            priority="High",
            deadline=None,
            source={"page": 4},
        )
    ]

    result = build_document_analysis_experience(
        overview=overview,
        type_workspace=workspace,
        suggestions=suggestions,
    )

    assert result["overview_title"] == "Plan at a glance"
    assert result["focus"] == "Verify the clean database path"
    assert result["focus_source"]["page"] == 4
    assert result["attention_count"] == 3
    assert result["attention"][0]["label"] == "Risk"
    assert result["action_count"] == 1
    assert result["actions"][0]["priority"] == "High"
    assert result["questions"][0]["question"] == "What could block launch?"
    assert result["plan_sections"][0]["label"] == "Objectives"
    assert result["plan_sections"][0]["source"]["page"] == 1


def test_experience_falls_back_to_analysis_actions_without_persisted_suggestions():
    result = build_document_analysis_experience(
        overview={
            "analysis": {
                "action_items": [
                    {
                        "title": "Review launch checklist",
                        "description": "Confirm every launch-critical flow.",
                        "priority": "Medium",
                        "deadline": None,
                        "source": {"page": 5},
                    }
                ],
                "risks": [],
                "missing_information": [],
                "deadlines": [],
                "key_points": [],
                "questions": [],
            }
        },
        type_workspace={
            "type_key": "general_reference",
            "type_label": "General Reference",
            "metadata": {},
            "populated_sections": [],
        },
        suggestions=[],
    )

    assert result["action_count"] == 1
    assert result["actions"][0]["title"] == "Review launch checklist"
    assert result["actions"][0]["persisted"] is False
    assert result["attention_count"] == 0


def test_experience_builds_professional_summary_from_grounded_analysis():
    result = build_document_analysis_experience(
        overview={
            "analysis": {
                "summary": "The document defines the release plan and launch controls.",
                "purpose": "Ship the release safely.",
                "key_points": [
                    {
                        "title": "Launch readiness is the immediate goal",
                        "detail": "All critical flows must pass before release.",
                        "source": {"page": 1, "evidence": "Launch readiness is required."},
                    }
                ],
                "requirements": [
                    {
                        "requirement": "Complete regression testing",
                        "details": "Authentication and planner flows must pass.",
                        "source": {"page": 2},
                    }
                ],
                "decisions": [
                    {
                        "decision": "Use staged rollout",
                        "reason": "Reduce deployment risk.",
                        "source": {"page": 3},
                    }
                ],
                "deadlines": [
                    {
                        "description": "Production launch",
                        "date": "2026-09-30",
                        "source": {"page": 4},
                    }
                ],
                "risks": [
                    {
                        "risk": "Unverified migration path",
                        "impact": "Deployment may fail.",
                        "source": {"page": 5},
                    }
                ],
                "missing_information": [
                    {
                        "question": "Who owns rollback?",
                        "why_it_matters": "Ownership affects recovery speed.",
                        "source": {"page": 6},
                    }
                ],
                "action_items": [],
                "questions": [],
            }
        },
        type_workspace={
            "type_key": "project_plan",
            "type_label": "Project Plan",
            "metadata": {},
            "populated_sections": [],
        },
        suggestions=[],
    )

    summary = result["professional_summary"]
    assert summary["executive_summary"].startswith("The document defines")
    assert summary["purpose"] == "Ship the release safely."
    assert summary["key_findings"][0]["title"] == "Launch readiness is the immediate goal"
    assert [item["label"] for item in summary["important_details"]] == [
        "Requirement",
        "Decision",
        "Date",
    ]
    assert summary["risks"][0]["title"] == "Unverified migration path"
    assert summary["gaps"][0]["title"] == "Who owns rollback?"
    assert summary["evidence"]["referenced_items"] == 6
    assert summary["evidence"]["total_items"] == 6
