"""LifeOS API v1 registration."""

from lifeos.api.v1.routes import api_v1_bp


def register_api_v1(app) -> None:
    app.register_blueprint(api_v1_bp)


__all__ = ["api_v1_bp", "register_api_v1"]
