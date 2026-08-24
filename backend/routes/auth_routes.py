"""Public authentication routes for LifeOS."""

from __future__ import annotations

from urllib.parse import urljoin, urlsplit

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy.exc import SQLAlchemyError

from services.auth_service import (
    AccountCreationError,
    DuplicateEmailError,
    authenticate_user,
    build_registration_input,
    claim_legacy_projects,
    create_user,
    normalize_email,
    validate_registration,
)


auth_bp = Blueprint("auth_bp", __name__)


def is_safe_redirect_url(target: str | None) -> bool:
    """Allow redirects only to pages on the current LifeOS host."""

    if not target:
        return False

    host_url = urlsplit(request.host_url)
    redirect_url = urlsplit(urljoin(request.host_url, target))

    return (
        redirect_url.scheme in ("http", "https")
        and host_url.netloc == redirect_url.netloc
    )


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        entered_name = (request.form.get("name") or "").strip()
        entered_email = (request.form.get("email") or "").strip()

        registration = build_registration_input(
            name=entered_name,
            email=entered_email,
            password=request.form.get("password"),
            confirm_password=request.form.get("confirm_password"),
        )

        validation_message = validate_registration(registration)
        if validation_message:
            flash(validation_message, "error")
        else:
            try:
                user = create_user(registration)
                login_user(user)
                flash(
                    "Your LifeOS account was created successfully.",
                    "success",
                )
                return redirect(url_for("dashboard"))
            except DuplicateEmailError:
                flash(
                    "An account with this email already exists.",
                    "error",
                )
            except AccountCreationError:
                current_app.logger.exception(
                    "LifeOS could not create a user account."
                )
                flash("The account could not be created.", "error")

        return render_template(
            "register.html",
            entered_name=entered_name,
            entered_email=entered_email,
        )

    return render_template("register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = normalize_email(request.form.get("email"))
        password = request.form.get("password", "")
        remember = request.form.get("remember") == "on"
        user = authenticate_user(email, password)

        if user is None:
            flash("Incorrect email or password.", "error")
            return render_template("login.html", entered_email=email)

        try:
            claim_legacy_projects(user)
        except SQLAlchemyError:
            current_app.logger.exception(
                "LifeOS could not claim legacy projects during login."
            )

        login_user(user, remember=remember)
        flash(f"Welcome back, {user.name}.", "success")

        next_page = request.args.get("next")
        if is_safe_redirect_url(next_page):
            return redirect(next_page)
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("landing"))
