from urllib.parse import urljoin, urlsplit

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy.exc import IntegrityError

from database import db
from models import Project, User


auth_bp = Blueprint("auth_bp", __name__)


def normalize_email(email):
    return (email or "").strip().lower()


def is_safe_redirect_url(target):
    if not target:
        return False

    host_url = urlsplit(request.host_url)
    redirect_url = urlsplit(urljoin(request.host_url, target))

    return (
        redirect_url.scheme in ("http", "https")
        and host_url.netloc == redirect_url.netloc
    )


def claim_legacy_projects(user):
    """Assign old ownerless development projects when only one user exists."""
    if User.query.count() != 1:
        return

    changed = (
        Project.query.filter(Project.user_id.is_(None))
        .update({Project.user_id: user.id}, synchronize_session=False)
    )

    if changed:
        db.session.commit()


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = normalize_email(request.form.get("email"))
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if len(name) < 2:
            flash("Please enter your full name.", "error")
        elif "@" not in email or "." not in email.rsplit("@", 1)[-1]:
            flash("Please enter a valid email address.", "error")
        elif len(password) < 8:
            flash("Password must contain at least 8 characters.", "error")
        elif password != confirm_password:
            flash("The passwords do not match.", "error")
        elif User.query.filter_by(email=email).first():
            flash("An account with this email already exists.", "error")
        else:
            user = User(name=name, email=email)
            user.set_password(password)

            try:
                db.session.add(user)
                db.session.commit()
                claim_legacy_projects(user)
                login_user(user)
                flash("Your LifeOS account was created successfully.", "success")
                return redirect(url_for("dashboard"))
            except IntegrityError:
                db.session.rollback()
                flash("An account with this email already exists.", "error")
            except Exception as error:
                db.session.rollback()
                print("Registration error:", error)
                flash("The account could not be created.", "error")

        return render_template(
            "register.html",
            entered_name=name,
            entered_email=email,
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
        user = User.query.filter_by(email=email).first()

        if not user or not user.check_password(password):
            flash("Incorrect email or password.", "error")
            return render_template("login.html", entered_email=email)

        claim_legacy_projects(user)
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
