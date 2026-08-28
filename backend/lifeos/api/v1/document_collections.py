"""React API for Document Collections (Step 17)."""
from __future__ import annotations
from flask import Blueprint, jsonify
from flask_login import current_user
from lifeos.api.v1.common import api_auth_required,json_body,not_found,persistence_error,validation_error
from lifeos.api.v1.serializers import serialize_document_collection,serialize_document_collection_question
from services.document_collection_service import DocumentCollectionNotFoundError,DocumentCollectionPersistenceError,DocumentCollectionValidationError,add_document_to_collection,create_collection,delete_collection,list_owned_collections,remove_document_from_collection,require_owned_collection,update_collection
from services.document_collection_question_workflow_service import CollectionQuestionNotFoundError,CollectionQuestionNotReadyError,CollectionQuestionWorkflowError,ask_owned_collection_documents,list_owned_collection_questions

document_collections_api_bp=Blueprint("api_v1_document_collections",__name__,url_prefix="/api/v1/document-collections")

@document_collections_api_bp.get("")
@api_auth_required
def list_collections_route():
    return jsonify({"items":[serialize_document_collection(x) for x in list_owned_collections(current_user.id)]})

@document_collections_api_bp.post("")
@api_auth_required
def create_collection_route():
    p=json_body()
    try: row=create_collection(user_id=current_user.id,name=p.get("name"),description=p.get("description"))
    except DocumentCollectionValidationError as e: return validation_error(str(e))
    except DocumentCollectionPersistenceError as e: return persistence_error(str(e))
    return jsonify({"item":serialize_document_collection(row,include_documents=True)}),201

@document_collections_api_bp.get("/<int:collection_id>")
@api_auth_required
def collection_details_route(collection_id:int):
    try:
        row=require_owned_collection(collection_id,current_user.id)
        qs=list_owned_collection_questions(collection_id=collection_id,user_id=current_user.id,limit=50)
    except (DocumentCollectionNotFoundError,CollectionQuestionNotFoundError): return not_found("Collection not found.")
    return jsonify({"item":serialize_document_collection(row,include_documents=True),"question_history":[serialize_document_collection_question(x) for x in qs]})

@document_collections_api_bp.patch("/<int:collection_id>")
@api_auth_required
def update_collection_route(collection_id:int):
    p=json_body()
    try: row=update_collection(collection_id=collection_id,user_id=current_user.id,name=p.get("name") if "name" in p else None,description=p.get("description") if "description" in p else None)
    except DocumentCollectionNotFoundError: return not_found("Collection not found.")
    except DocumentCollectionValidationError as e: return validation_error(str(e))
    except DocumentCollectionPersistenceError as e: return persistence_error(str(e))
    return jsonify({"item":serialize_document_collection(row,include_documents=True)})

@document_collections_api_bp.delete("/<int:collection_id>")
@api_auth_required
def delete_collection_route(collection_id:int):
    try: name=delete_collection(collection_id=collection_id,user_id=current_user.id)
    except DocumentCollectionNotFoundError: return not_found("Collection not found.")
    except DocumentCollectionPersistenceError as e: return persistence_error(str(e))
    return jsonify({"deleted":True,"name":name})

@document_collections_api_bp.post("/<int:collection_id>/documents")
@api_auth_required
def add_collection_document_route(collection_id:int):
    p=json_body()
    try: did=int(p.get("document_id"))
    except (TypeError,ValueError): return validation_error("Select a valid document.")
    try:
        add_document_to_collection(collection_id=collection_id,document_id=did,user_id=current_user.id)
        row=require_owned_collection(collection_id,current_user.id)
    except DocumentCollectionNotFoundError as e: return not_found(str(e))
    except DocumentCollectionValidationError as e: return validation_error(str(e))
    except DocumentCollectionPersistenceError as e: return persistence_error(str(e))
    return jsonify({"item":serialize_document_collection(row,include_documents=True)})

@document_collections_api_bp.delete("/<int:collection_id>/documents/<int:document_id>")
@api_auth_required
def remove_collection_document_route(collection_id:int,document_id:int):
    try:
        remove_document_from_collection(collection_id=collection_id,document_id=document_id,user_id=current_user.id)
        row=require_owned_collection(collection_id,current_user.id)
    except DocumentCollectionNotFoundError as e: return not_found(str(e))
    except DocumentCollectionPersistenceError as e: return persistence_error(str(e))
    return jsonify({"removed":True,"item":serialize_document_collection(row,include_documents=True)})

@document_collections_api_bp.post("/<int:collection_id>/questions")
@api_auth_required
def ask_collection_route(collection_id:int):
    p=json_body()
    try: result=ask_owned_collection_documents(collection_id=collection_id,user_id=current_user.id,question_text=p.get("question"),force=bool(p.get("force")))
    except CollectionQuestionNotFoundError: return not_found("Collection not found.")
    except CollectionQuestionNotReadyError as e: return validation_error(str(e))
    except CollectionQuestionWorkflowError as e: return jsonify({"error":"question_failed","message":str(e)}),503
    return jsonify({"item":serialize_document_collection_question(result.question),"reused_existing":result.reused_existing})

@document_collections_api_bp.get("/<int:collection_id>/questions")
@api_auth_required
def collection_questions_route(collection_id:int):
    try: rows=list_owned_collection_questions(collection_id=collection_id,user_id=current_user.id,limit=50)
    except CollectionQuestionNotFoundError: return not_found("Collection not found.")
    return jsonify({"items":[serialize_document_collection_question(x) for x in rows]})
