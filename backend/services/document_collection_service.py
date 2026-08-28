"""Ownership-safe CRUD for user-defined document collections (Step 17)."""
from __future__ import annotations
from sqlalchemy.exc import SQLAlchemyError
from database import db
from models import DocumentCollection, DocumentCollectionItem
from services.document_access_service import DocumentNotFoundError, require_owned_document

class DocumentCollectionError(RuntimeError): pass
class DocumentCollectionNotFoundError(DocumentCollectionError): pass
class DocumentCollectionValidationError(DocumentCollectionError): pass
class DocumentCollectionPersistenceError(DocumentCollectionError): pass

def list_owned_collections(user_id:int)->list[DocumentCollection]:
    return DocumentCollection.query.filter_by(user_id=user_id).order_by(DocumentCollection.updated_at.desc(),DocumentCollection.id.desc()).all()

def require_owned_collection(collection_id:int,user_id:int)->DocumentCollection:
    row=DocumentCollection.query.filter_by(id=collection_id,user_id=user_id).first()
    if row is None: raise DocumentCollectionNotFoundError("Collection not found.")
    return row

def create_collection(*,user_id:int,name:str,description:str|None=None)->DocumentCollection:
    row=DocumentCollection(user_id=user_id,name=_name(name),description=_description(description))
    try: db.session.add(row); db.session.commit()
    except SQLAlchemyError as e: db.session.rollback(); raise DocumentCollectionPersistenceError("LifeOS could not create the collection.") from e
    return row

def update_collection(*,collection_id:int,user_id:int,name=None,description=None)->DocumentCollection:
    row=require_owned_collection(collection_id,user_id)
    if name is not None: row.name=_name(name)
    if description is not None: row.description=_description(description)
    try: db.session.commit()
    except SQLAlchemyError as e: db.session.rollback(); raise DocumentCollectionPersistenceError("LifeOS could not update the collection.") from e
    return row

def delete_collection(*,collection_id:int,user_id:int)->str:
    row=require_owned_collection(collection_id,user_id); name=row.name
    try: db.session.delete(row); db.session.commit()
    except SQLAlchemyError as e: db.session.rollback(); raise DocumentCollectionPersistenceError("LifeOS could not delete the collection.") from e
    return name

def add_document_to_collection(*,collection_id:int,document_id:int,user_id:int)->DocumentCollectionItem:
    collection=require_owned_collection(collection_id,user_id)
    try: document=require_owned_document(document_id,user_id)
    except DocumentNotFoundError as e: raise DocumentCollectionNotFoundError("Document not found.") from e
    if not bool(getattr(document, "is_current_version", True)):
        raise DocumentCollectionValidationError(
            "Add the current version of this document to the collection."
        )
    existing=DocumentCollectionItem.query.filter_by(collection_id=collection.id,document_id=document.id).first()
    if existing is not None: return existing
    item=DocumentCollectionItem(collection_id=collection.id,document_id=document.id)
    try: db.session.add(item); db.session.commit()
    except SQLAlchemyError as e: db.session.rollback(); raise DocumentCollectionPersistenceError("LifeOS could not add the document to the collection.") from e
    return item

def remove_document_from_collection(*,collection_id:int,document_id:int,user_id:int)->None:
    collection=require_owned_collection(collection_id,user_id)
    item=DocumentCollectionItem.query.filter_by(collection_id=collection.id,document_id=document_id).first()
    if item is None: raise DocumentCollectionNotFoundError("The document is not in this collection.")
    try: db.session.delete(item); db.session.commit()
    except SQLAlchemyError as e: db.session.rollback(); raise DocumentCollectionPersistenceError("LifeOS could not remove the document from the collection.") from e

def _name(v)->str:
    c=" ".join(str(v or "").split()).strip()
    if not c: raise DocumentCollectionValidationError("Collection name is required.")
    if len(c)>150: raise DocumentCollectionValidationError("Collection name cannot exceed 150 characters.")
    return c

def _description(v)->str|None:
    c=str(v or "").strip(); return c[:4000] or None
