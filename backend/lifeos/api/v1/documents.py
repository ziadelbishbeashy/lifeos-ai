"""Small document-list API used while advanced Document Brain stays on legacy UI."""

from __future__ import annotations

from flask import Blueprint, jsonify
from flask_login import current_user

from lifeos.api.v1.common import api_auth_required
from lifeos.api.v1.serializers import serialize_document_summary
from lifeos.domains.documents.facade import list_owned_documents


documents_api_bp = Blueprint(
    "api_v1_documents",
    __name__,
    url_prefix="/api/v1/documents",
)


@documents_api_bp.get("")
@api_auth_required
def documents():
    rows = [row for row in list_owned_documents(current_user.id) if row.is_current_version]
    return jsonify({"items": [serialize_document_summary(row) for row in rows]})
