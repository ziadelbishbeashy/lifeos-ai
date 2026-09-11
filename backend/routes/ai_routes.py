from flask import Blueprint, render_template, request
from flask_login import login_required

from services.ai_service import (
    AIServiceError,
    get_ai_configuration,
    summarize_text,
)


ai_bp = Blueprint(
    "ai_bp",
    __name__,
    url_prefix="/ai",
)


@ai_bp.route("/test", methods=["GET", "POST"])
@login_required
def test_ai():
    input_text = ""
    result = None
    error_message = None
    provider_info = None

    try:
        configuration = get_ai_configuration()

        provider_info = {
            "provider": configuration["provider"],
            "model": configuration["model"],
        }

    except AIServiceError as error:
        error_message = str(error)

    if request.method == "POST":
        input_text = request.form.get("input_text", "").strip()

        try:
            result = summarize_text(input_text)

        except AIServiceError as error:
            error_message = str(error)

    return render_template(
        "ai_test.html",
        input_text=input_text,
        result=result,
        error_message=error_message,
        provider_info=provider_info,
    )