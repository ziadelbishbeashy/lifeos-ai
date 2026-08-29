from __future__ import annotations

import pytest

from database import db
from models import (
    Document,
    LearningModule,
    LifeOSContextLink,
    ModuleTaskLink,
    Project,
    Task,
    User,
)
from services.context_connection_service import (
    ContextConnectionNotFoundError,
    build_owned_context_connections,
)
from services.intelligence_action_service import (
    confirm_owned_action_proposal,
    create_priority_action_proposal,
)
from services.intelligence_ask_service import ask_lifeos
from services.intelligence_intent_router_service import route_intelligence_request


def _project(user_id: int, title: str = "LifeOS") -> Project:
    project = Project(user_id=user_id, title=title, status="In Progress", priority="Medium", progress=15)
    db.session.add(project)
    db.session.commit()
    return project


def _document(user_id: int, project_id: int, filename: str = "Architecture.pdf") -> Document:
    document = Document(
        user_id=user_id,
        project_id=project_id,
        filename=filename,
        file_path=f"test/{filename}",
        extracted_text="Current architecture evidence.",
        is_current_version=True,
    )
    db.session.add(document)
    db.session.commit()
    return document


def _document_priority(project: Project, document: Document) -> dict:
    return {
        "project_id": project.id,
        "project_title": project.title,
        "category": "document_risk",
        "severity": "high",
        "title": "Review documented risk: Fragile integration",
        "reason": "The current architecture document records an integration risk.",
        "recommended_action": "Create a mitigation task and verify the integration boundary.",
        "evidence": [
            {
                "source_type": "document",
                "source_id": document.id,
                "label": document.filename,
                "field": "risk",
                "freshness": "current",
            }
        ],
    }


def test_i13_structural_graph_unifies_project_and_module_links(app, user):
    with app.app_context():
        project = _project(user)
        task = Task(
            user_id=user,
            project_id=project.id,
            title="Implement graph",
            status="Pending",
            importance="High",
            difficulty="Medium",
        )
        module = LearningModule(user_id=user, title="Operating Systems", status="Active")
        db.session.add_all([task, module])
        db.session.flush()
        db.session.add(ModuleTaskLink(module_id=module.id, task_id=task.id))
        db.session.commit()

        result = build_owned_context_connections(owner_id=user, resource_type="task", resource_id=task.id)
        pairs = {(item.relation_type, item.resource.resource_type, item.resource.resource_id) for item in result.connections}
        assert ("belongs_to_project", "project", project.id) in pairs
        assert ("module_resource", "module", module.id) in pairs
        assert result.to_dict()["verified_from_state"] is True
        assert result.to_dict()["read_only"] is True


def test_i13_confirmed_i9_task_persists_document_provenance(app, user):
    with app.app_context():
        project = _project(user)
        document = _document(user, project.id)
        proposal = create_priority_action_proposal(
            owner_id=user,
            action_type="create_task",
            priority=_document_priority(project, document),
        )
        confirmed = confirm_owned_action_proposal(proposal_id=proposal.id, owner_id=user)
        assert confirmed.execution_resource_type == "task"

        task_id = int(confirmed.execution_resource_id)
        link = LifeOSContextLink.query.filter_by(
            user_id=user,
            source_type="task",
            source_id=task_id,
            target_type="document",
            target_id=document.id,
            relation_type="derived_from",
        ).one()
        assert link.provenance_type == "ask_lifeos"
        assert link.provenance_id == proposal.id
        assert link.evidence[0]["label"] == document.filename

        task_graph = build_owned_context_connections(owner_id=user, resource_type="task", resource_id=task_id)
        source = next(item for item in task_graph.connections if item.resource.resource_type == "document")
        assert source.relation_label == "Derived from"
        assert source.resource.label == document.filename


def test_i13_document_can_trace_tasks_created_from_it_and_ask_lifeos_routes_it(app, user):
    with app.app_context():
        project = _project(user)
        document = _document(user, project.id, "Deployment_Plan.pdf")
        proposal = create_priority_action_proposal(
            owner_id=user,
            action_type="create_task",
            priority=_document_priority(project, document),
        )
        confirmed = confirm_owned_action_proposal(proposal_id=proposal.id, owner_id=user)
        task = Task.query.get(int(confirmed.execution_resource_id))

        route = route_intelligence_request(
            query="Which tasks came from Deployment_Plan.pdf?",
            owner_id=user,
        )
        assert route.intent == "context_connections"

        answer = ask_lifeos(query="Which tasks came from Deployment_Plan.pdf?", owner_id=user).to_dict()
        assert answer["response_mode"] == "deterministic_verified"
        assert answer["connections"]["resource"]["id"] == document.id
        connected_tasks = [item for item in answer["connections"]["connections"] if item["resource"]["type"] == "task"]
        assert any(item["resource"]["id"] == task.id for item in connected_tasks)
        assert all(item["relation_type"] == "derived_from" for item in connected_tasks)


def test_i13_context_connections_are_owner_isolated(app, user):
    with app.app_context():
        project = _project(user)
        task = Task(user_id=user, project_id=project.id, title="Private task", status="Pending", importance="Medium", difficulty="Medium")
        db.session.add(task)

        other = User(name="Other", email="i13-other@example.com")
        other.set_password("StrongPass123!")
        db.session.add(other)
        db.session.commit()

        with pytest.raises(ContextConnectionNotFoundError):
            build_owned_context_connections(owner_id=other.id, resource_type="task", resource_id=task.id)

        answer = ask_lifeos(query=f"Show connections for task #{task.id}", owner_id=other.id).to_dict()
        assert answer["connections"]["resource"] is None
        assert str(task.id) not in answer["answer"]


def _login(client):
    return client.post(
        "/login",
        data={"email": "student@example.com", "password": "StrongPass123!"},
        follow_redirects=False,
    )


def test_i13_connections_api_returns_verified_product_packet(client, app, user):
    with app.app_context():
        project = _project(user)
        document = _document(user, project.id)
        document_id = document.id

    _login(client)
    response = client.get(f"/api/v1/intelligence/connections/document/{document_id}")
    assert response.status_code == 200
    packet = response.get_json()["connections"]
    assert packet["verified_from_state"] is True
    assert packet["read_only"] is True
    assert packet["resource"]["label"] == "Architecture.pdf"
    assert any(item["resource"]["type"] == "project" for item in packet["connections"])
    raw = str(packet).casefold()
    assert "embedding" not in raw
    assert "system prompt" not in raw
