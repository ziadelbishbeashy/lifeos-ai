"""LifeOS application factory for Foundation V2."""

from __future__ import annotations

import click
import json
from click import ClickException
from flask import Flask
from pathlib import Path
from werkzeug.middleware.proxy_fix import ProxyFix

from lifeos.api.v1 import register_api_v1
from lifeos.core.config import CONFIG_BY_NAME, get_config_name, validate_config
from lifeos.core.database import db
from lifeos.core.extensions import init_extensions, login_manager

from error_handlers import register_error_handlers
from logging_config import configure_logging
from jobs.document_ocr import register_document_ocr_job
from models import User
from routes.ai_routes import ai_bp
from routes.analytics_routes import analytics_bp
from routes.auth_routes import auth_bp
from routes.dashboard_routes import register_dashboard_routes
from routes.document_routes import document_bp
from routes.focus_routes import focus_bp
from routes.note_routes import note_bp
from routes.notification_routes import notification_bp
from routes.project_routes import project_bp
from routes.task_routes import task_bp
from security import init_security
from services.scheduler_service import run_notification_check_once


@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


def register_legacy_web_blueprints(app: Flask) -> None:
    """Register proven web controllers used by the React UI parity bridge."""

    app.register_blueprint(auth_bp)
    app.register_blueprint(project_bp)
    app.register_blueprint(task_bp)
    app.register_blueprint(notification_bp)
    app.register_blueprint(focus_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(note_bp)
    app.register_blueprint(document_bp)


def register_commands(app: Flask) -> None:
    @app.cli.command("init-db")
    def init_db_command():
        """Create missing tables only for local/development bootstrapping."""

        if app.config.get("ENV_NAME") == "production":
            raise ClickException(
                "init-db is disabled in production. Use a reviewed PostgreSQL baseline/migration."
            )
        db.create_all()
        print("LifeOS database tables are ready.")

    @app.cli.command("notifications-once")
    def notifications_once_command():
        result = run_notification_check_once(app)
        print(result)

    @app.cli.command("diagnose")
    def diagnose_command():
        uri = str(app.config.get("SQLALCHEMY_DATABASE_URI") or "")
        if uri.startswith("postgresql"):
            database_family = "postgresql"
        elif uri.startswith("mssql"):
            database_family = "legacy-sqlserver"
        elif uri.startswith("sqlite"):
            database_family = "sqlite"
        else:
            database_family = "other"
        print(f"environment={app.config.get('ENV_NAME')}")
        print(f"database_family={database_family}")
        print(f"database_configured={bool(uri)}")
        print(f"storage_backend={app.config.get('STORAGE_BACKEND')}")
        print(f"job_backend={app.config.get('JOB_BACKEND')}")
        print(f"scheduler_enabled={bool(app.config.get('ENABLE_EMAIL_SCHEDULER'))}")
        print("architecture=foundation-v2")

    @app.cli.command("resource-limits")
    def resource_limits_command():
        """Print the active Step 20 resource/cost policy."""

        from services.resource_limit_service import (
            format_resource_limits_summary,
            get_resource_limits,
        )

        click.echo(format_resource_limits_summary(get_resource_limits()))

    @app.cli.command("intelligence-project-review")
    @click.option(
        "--user-id",
        type=click.IntRange(min=1),
        required=True,
        help="Owned LifeOS user whose project should be reviewed.",
    )
    @click.option(
        "--project-id",
        type=click.IntRange(min=1),
        required=True,
        help="Project to review using the read-only Intelligence Core.",
    )
    def intelligence_project_review_command(user_id, project_id):
        """Run the first read-only planner -> tools -> verified project review."""

        from services.project_review_intelligence_service import review_owned_project
        from services.workspace_context_service import WorkspaceContextNotFoundError

        try:
            review = review_owned_project(
                project_id=project_id,
                owner_id=user_id,
            )
        except WorkspaceContextNotFoundError as error:
            raise ClickException(str(error)) from error

        click.echo(json.dumps(review.to_dict(), indent=2, ensure_ascii=False))

    @app.cli.command("intelligence-project-agent")
    @click.option(
        "--user-id",
        type=click.IntRange(min=1),
        required=True,
        help="Owned LifeOS user whose project should be prioritized.",
    )
    @click.option(
        "--project-id",
        type=click.IntRange(min=1),
        required=True,
        help="Project to inspect using the read-only constrained Project Review Agent.",
    )
    def intelligence_project_agent_command(user_id, project_id):
        """Run I8 inspect -> prioritize -> recommend over trusted project state."""

        from services.project_review_agent_service import run_owned_project_review_agent
        from services.workspace_context_service import WorkspaceContextNotFoundError

        try:
            result = run_owned_project_review_agent(
                project_id=project_id,
                owner_id=user_id,
            )
        except WorkspaceContextNotFoundError as error:
            raise ClickException(str(error)) from error

        click.echo(json.dumps(result.to_dict(include_diagnostics=True), indent=2, ensure_ascii=False))

    @app.cli.command("intelligence-portfolio-agent")
    @click.option(
        "--user-id",
        type=click.IntRange(min=1),
        required=True,
        help="Owned LifeOS user whose projects should be prioritized.",
    )
    def intelligence_portfolio_agent_command(user_id):
        """Run I8 portfolio prioritization across owned projects."""

        from services.project_review_agent_service import run_owned_portfolio_review_agent

        result = run_owned_portfolio_review_agent(owner_id=user_id)
        click.echo(json.dumps(result.to_dict(include_diagnostics=True), indent=2, ensure_ascii=False))

    @app.cli.command("intelligence-route")
    @click.option(
        "--user-id",
        type=click.IntRange(min=1),
        required=True,
        help="Owned LifeOS user whose request should be routed.",
    )
    @click.option(
        "--query",
        type=str,
        required=True,
        help="Natural-language Ask LifeOS request.",
    )
    def intelligence_route_command(user_id, query):
        """Route one natural-language request through the I2/I3 read-only core."""

        from services.intelligence_intent_router_service import IntelligenceRouterError
        from services.intelligence_request_service import handle_intelligence_request
        from services.workspace_context_service import WorkspaceContextNotFoundError

        try:
            result = handle_intelligence_request(query=query, owner_id=user_id)
        except (IntelligenceRouterError, WorkspaceContextNotFoundError) as error:
            raise ClickException(str(error)) from error

        click.echo(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))

    @app.cli.command("intelligence-ask")
    @click.option(
        "--user-id",
        type=click.IntRange(min=1),
        required=True,
        help="Owned LifeOS user whose request should be answered.",
    )
    @click.option(
        "--query",
        type=str,
        required=True,
        help="Natural-language Ask LifeOS request.",
    )
    def intelligence_ask_command(user_id, query):
        """Run the first I4/I5 verified natural Ask LifeOS workflow."""

        from services.intelligence_ask_service import ask_lifeos
        from services.intelligence_intent_router_service import IntelligenceRouterError
        from services.workspace_context_service import WorkspaceContextNotFoundError

        try:
            result = ask_lifeos(query=query, owner_id=user_id)
        except (IntelligenceRouterError, WorkspaceContextNotFoundError) as error:
            raise ClickException(str(error)) from error

        click.echo(json.dumps(result.to_dict(include_diagnostics=True), indent=2, ensure_ascii=False))

    @app.cli.command("intelligence-activity")
    @click.option("--user-id", type=click.IntRange(min=1), required=True)
    @click.option("--query", type=str, default="What changed recently?", show_default=True)
    @click.option("--project-id", type=click.IntRange(min=1), required=False)
    def intelligence_activity_command(user_id, query, project_id):
        """Print the I10 deterministic recent-activity view."""

        from services.lifeos_activity_service import build_owned_recent_activity

        try:
            result = build_owned_recent_activity(
                owner_id=user_id,
                query=query,
                project_id=project_id,
            )
        except LookupError as error:
            raise ClickException(str(error)) from error
        click.echo(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))

    @app.cli.command("intelligence-events")
    @click.option("--user-id", type=click.IntRange(min=1), required=True)
    def intelligence_events_command(user_id):
        """Run the I14 trusted event scan and print normalized events."""

        from services.intelligence_event_service import scan_owned_intelligence_events

        result = scan_owned_intelligence_events(owner_id=user_id)
        click.echo(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))

    @app.cli.command("intelligence-proactive")
    @click.option("--user-id", type=click.IntRange(min=1), required=True)
    def intelligence_proactive_command(user_id):
        """Refresh I14 then print I15 in-app proactive notices."""

        from services.proactive_intelligence_service import refresh_owned_proactive_notifications

        result = refresh_owned_proactive_notifications(owner_id=user_id)
        click.echo(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))

    @app.cli.command("intelligence-memory")
    @click.option("--user-id", type=click.IntRange(min=1), required=True)
    def intelligence_memory_command(user_id):
        """Refresh and print I16 inspectable structured memory."""

        from services.structured_memory_service import refresh_owned_structured_memory

        result = refresh_owned_structured_memory(owner_id=user_id)
        click.echo(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))

    @app.cli.command("automation-registry")
    def automation_registry_command():
        """Print the I17 allow-listed automation contracts and safety boundary."""

        from services.automation_service import automation_registry

        click.echo(json.dumps(automation_registry(), indent=2, ensure_ascii=False))

    @app.cli.command("automation-list")
    @click.option("--user-id", type=click.IntRange(min=1), required=True)
    def automation_list_command(user_id):
        """List owned I17 automation definitions."""

        from services.automation_service import automation_to_dict, list_owned_automations

        items = list_owned_automations(owner_id=user_id)
        click.echo(json.dumps([automation_to_dict(item) for item in items], indent=2, ensure_ascii=False))

    @app.cli.command("automation-candidates")
    @click.option("--user-id", type=click.IntRange(min=1), required=True)
    def automation_candidates_command(user_id):
        """Evaluate which I17 rules would fire without executing them."""

        from services.automation_engine_service import collect_owned_automation_candidates

        result = collect_owned_automation_candidates(owner_id=user_id)
        click.echo(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))

    @app.cli.command("automation-preview")
    @click.option("--user-id", type=click.IntRange(min=1), required=True)
    @click.option("--automation-id", type=click.IntRange(min=1), required=True)
    @click.option("--event-id", type=click.IntRange(min=1), required=False)
    def automation_preview_command(user_id, automation_id, event_id):
        """Run one read-only I17 preview and persist its audit record."""

        from services.automation_service import (
            AutomationNotFoundError,
            AutomationValidationError,
            preview_owned_automation,
        )

        try:
            result = preview_owned_automation(
                owner_id=user_id,
                automation_id=automation_id,
                event_id=event_id,
            )
        except (AutomationNotFoundError, AutomationValidationError) as error:
            raise ClickException(str(error)) from error
        click.echo(json.dumps(result.to_dict(), indent=2, ensure_ascii=False, default=str))

    @app.cli.command("automation-run")
    @click.option("--user-id", type=click.IntRange(min=1), required=True)
    @click.option("--automation-id", type=click.IntRange(min=1), required=True)
    def automation_run_command(user_id, automation_id):
        """Run one reviewed I17 automation now and deliver its in-app result."""

        from services.automation_engine_service import execute_owned_automation
        from services.automation_service import AutomationNotFoundError, AutomationValidationError

        try:
            result = execute_owned_automation(
                owner_id=user_id,
                automation_id=automation_id,
                trigger_source="manual",
            )
        except (AutomationNotFoundError, AutomationValidationError) as error:
            raise ClickException(str(error)) from error
        click.echo(json.dumps(result.to_dict(), indent=2, ensure_ascii=False, default=str))

    @app.cli.command("automation-run-due")
    @click.option("--user-id", type=click.IntRange(min=1), required=True)
    def automation_run_due_command(user_id):
        """Execute this user's currently due/matching I17 automations once."""

        from services.automation_engine_service import execute_owned_automation_cycle

        result = execute_owned_automation_cycle(owner_id=user_id)
        click.echo(json.dumps(result.to_dict(), indent=2, ensure_ascii=False, default=str))

    @app.cli.command("intelligence-project-context")
    @click.option(
        "--user-id",
        type=click.IntRange(min=1),
        required=True,
    )
    @click.option(
        "--project-id",
        type=click.IntRange(min=1),
        required=True,
    )
    def intelligence_project_context_command(user_id, project_id):
        """Print the trusted I2 project context packet without raw tool internals."""

        from services.intelligence_context_service import collect_owned_project_context
        from services.workspace_context_service import WorkspaceContextNotFoundError

        try:
            context = collect_owned_project_context(
                project_id=project_id,
                owner_id=user_id,
            )
        except WorkspaceContextNotFoundError as error:
            raise ClickException(str(error)) from error

        click.echo(
            json.dumps(
                context.to_dict(include_tool_data=False),
                indent=2,
                ensure_ascii=False,
            )
        )

    @app.cli.command("rag-eval")
    @click.option(
        "--dataset",
        type=click.Path(exists=True, dir_okay=False, path_type=Path),
        required=True,
        help="Path to a Step 18 gold evaluation JSON dataset.",
    )
    @click.option(
        "--user-id",
        type=click.IntRange(min=1),
        required=True,
        help="Owned LifeOS user whose documents/workspaces are evaluated.",
    )
    @click.option(
        "--mode",
        type=click.Choice(["retrieval", "full"], case_sensitive=False),
        default="retrieval",
        show_default=True,
        help="retrieval avoids answer-provider calls; full also grades answers/citations.",
    )
    @click.option(
        "--top-k",
        type=click.IntRange(min=1, max=12),
        default=None,
        help="Override dataset/default retrieval depth.",
    )
    @click.option(
        "--output",
        type=click.Path(dir_okay=False, path_type=Path),
        default=None,
        help="Optional JSON report path.",
    )
    @click.option(
        "--no-fail",
        is_flag=True,
        help="Print failures without returning a failing CLI exit code.",
    )
    def rag_eval_command(dataset, user_id, mode, top_k, output, no_fail):
        """Run Step 18 RAG regression evaluation against the current database."""

        from services.rag_evaluation_service import (
            RagEvaluationError,
            format_rag_evaluation_summary,
            run_rag_evaluation,
            write_rag_evaluation_report,
        )

        try:
            report = run_rag_evaluation(
                dataset_path=dataset,
                user_id=user_id,
                mode=mode,
                top_k=top_k,
            )
        except RagEvaluationError as error:
            raise ClickException(str(error)) from error

        click.echo(format_rag_evaluation_summary(report))
        if output is not None:
            written = write_rag_evaluation_report(report, output)
            click.echo(f"report={written}")

        if not report.get("passed") and not no_fail:
            raise ClickException("Step 18 RAG evaluation did not meet the gold baseline.")

    @app.cli.command("security-eval")
    @click.option(
        "--dataset",
        type=click.Path(exists=True, dir_okay=False, path_type=Path),
        required=True,
        help="Path to a Step 19 prompt-injection evaluation JSON dataset.",
    )
    @click.option(
        "--mode",
        type=click.Choice(["static", "live"], case_sensitive=False),
        default="static",
        show_default=True,
        help="static inspects the attack corpus; live also calls the configured AI provider.",
    )
    @click.option(
        "--output",
        type=click.Path(dir_okay=False, path_type=Path),
        default=None,
        help="Optional JSON report path.",
    )
    @click.option(
        "--no-fail",
        is_flag=True,
        help="Print failures without returning a failing CLI exit code.",
    )
    def security_eval_command(dataset, mode, output, no_fail):
        """Run Step 19 synthetic prompt-injection regression evaluation."""

        from services.security_evaluation_service import (
            SecurityEvaluationError,
            format_security_evaluation_summary,
            run_security_evaluation,
            write_security_evaluation_report,
        )

        try:
            report = run_security_evaluation(
                dataset_path=dataset,
                mode=mode,
            )
        except SecurityEvaluationError as error:
            raise ClickException(str(error)) from error

        click.echo(format_security_evaluation_summary(report))
        if output is not None:
            written = write_security_evaluation_report(report, output)
            click.echo(f"report={written}")

        if not report.get("passed") and not no_fail:
            raise ClickException("Step 19 security evaluation did not meet the security baseline.")


def create_app(
    config_name: str | None = None,
    test_config: dict | None = None,
) -> Flask:
    selected_config = config_name or get_config_name()
    config_class = CONFIG_BY_NAME.get(selected_config, CONFIG_BY_NAME["development"])

    backend_dir = Path(__file__).resolve().parents[1]
    application = Flask(
        __name__,
        template_folder=str(backend_dir / "templates"),
        static_folder=str(backend_dir / "static"),
        static_url_path="/static",
    )
    application.config.from_object(config_class)

    if test_config:
        application.config.update(test_config)

    validate_config(application)
    configure_logging(application)

    if application.config.get("TRUST_PROXY_HEADERS"):
        application.wsgi_app = ProxyFix(
            application.wsgi_app,
            x_for=1,
            x_proto=1,
            x_host=1,
            x_port=1,
        )

    init_extensions(application)
    register_document_ocr_job()
    register_legacy_web_blueprints(application)
    register_api_v1(application)
    register_dashboard_routes(application)
    register_error_handlers(application)
    init_security(application)
    register_commands(application)

    return application
