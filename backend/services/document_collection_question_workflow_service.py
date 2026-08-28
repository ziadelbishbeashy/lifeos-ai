"""Persistent grounded Q&A across document collections (Step 17)."""
from __future__ import annotations
import hashlib, json
from dataclasses import dataclass
from typing import Any
from sqlalchemy.exc import SQLAlchemyError
from database import db
from models import Document,DocumentCollection,DocumentCollectionItem,DocumentCollectionQuestion
from services.ai_service import AIServiceError,MAX_QUESTION_CHARACTERS,ask_document_collection_question,get_ai_configuration
from services.document_answerability_service import DocumentAnswerabilityError,verify_document_answerability
from services.document_collection_retrieval_service import CollectionRetrievalError,CollectionRetrievalNotFoundError,CollectionRetrievalNotReadyError,CollectionRetrievalValidationError,CollectionRetrievalResult,build_collection_context,retrieve_owned_collection_chunks,select_collection_sources
from services.document_evidence_preview_service import build_focused_evidence_preview
from services.document_version_service import current_document_filter
COLLECTION_QUESTION_WORKFLOW_VERSION="document-collection-rag-v1"
NO_MATCH_ANSWER="LifeOS could not find enough evidence across this document collection to answer that question."
class CollectionQuestionWorkflowError(RuntimeError): pass
class CollectionQuestionNotFoundError(CollectionQuestionWorkflowError): pass
class CollectionQuestionNotReadyError(CollectionQuestionWorkflowError): pass
@dataclass(frozen=True)
class SavedCollectionQuestion:
    collection:DocumentCollection; question:DocumentCollectionQuestion; reused_existing:bool

def ask_owned_collection_documents(*,collection_id:int,user_id:int,question_text:str,force:bool=False)->SavedCollectionQuestion:
    collection=_find(collection_id,user_id); q=" ".join(str(question_text or "").split()).strip()
    if not q: raise CollectionQuestionWorkflowError("Enter a question about the collection documents.")
    if len(q)>MAX_QUESTION_CHARACTERS: raise CollectionQuestionWorkflowError(f"The question is too long. Use at most {MAX_QUESTION_CHARACTERS:,} characters.")
    fp=create_collection_source_fingerprint(collection_id=collection.id,user_id=user_id)
    if not force:
        existing=(DocumentCollectionQuestion.query.filter_by(collection_id=collection.id,user_id=user_id,question=q,status="Completed",source_fingerprint=fp).order_by(DocumentCollectionQuestion.created_at.desc(),DocumentCollectionQuestion.id.desc()).first())
        if existing is not None: return SavedCollectionQuestion(collection,existing,True)
    try: retrieval=retrieve_owned_collection_chunks(collection_id=collection.id,user_id=user_id,query=q)
    except CollectionRetrievalNotFoundError as e: raise CollectionQuestionNotFoundError(str(e)) from e
    except CollectionRetrievalNotReadyError as e: raise CollectionQuestionNotReadyError(str(e)) from e
    except (CollectionRetrievalValidationError,CollectionRetrievalError) as e: _save_failed(collection,user_id,q,fp,e); raise CollectionQuestionWorkflowError(str(e)) from e
    context=build_collection_context(retrieval); answer_retrieval=retrieval
    if not context: result=_no_match(q,"lifeos","collection-hybrid-retrieval")
    else:
        try: verification=verify_document_answerability(filename=f"Collection: {collection.name}",retrieved_context=context,question=q)
        except DocumentAnswerabilityError as e: _save_failed(collection,user_id,q,fp,e); raise CollectionQuestionWorkflowError(str(e)) from e
        if not verification.answerable: result=_no_match(q,verification.provider,f"{verification.model}:answerability")
        else:
            try: answer_retrieval=select_collection_sources(retrieval_result=retrieval,source_ids=verification.source_ids)
            except CollectionRetrievalValidationError as e: _save_failed(collection,user_id,q,fp,e); raise CollectionQuestionWorkflowError(str(e)) from e
            try: result=ask_document_collection_question(collection_name=collection.name,retrieved_context=build_collection_context(answer_retrieval),question=q)
            except AIServiceError as e: _save_failed(collection,user_id,q,fp,e); raise CollectionQuestionWorkflowError(str(e)) from e
    sources=[]; answer=str(result.get("answer") or "").strip()
    if result.get("found_in_document"):
        claims=result.get("claims") or []; sources=_sources(answer_retrieval,claims); answer=_answer(claims)
    if not answer: raise CollectionQuestionWorkflowError("LifeOS generated an empty collection answer.")
    row=DocumentCollectionQuestion(collection_id=collection.id,user_id=user_id,question=q,answer=answer,sources_json=json.dumps(sources,ensure_ascii=False),provider=str(result.get("provider") or "unknown")[:30],model=str(result.get("model") or "unknown")[:100],status="Completed",source_fingerprint=fp,error_message=None)
    try: db.session.add(row); db.session.commit()
    except SQLAlchemyError as e: db.session.rollback(); raise CollectionQuestionWorkflowError("LifeOS generated the answer but could not save it.") from e
    return SavedCollectionQuestion(collection,row,False)

def list_owned_collection_questions(*,collection_id:int,user_id:int,limit:int=50):
    c=_find(collection_id,user_id)
    return DocumentCollectionQuestion.query.filter_by(collection_id=c.id,user_id=user_id).order_by(DocumentCollectionQuestion.created_at.desc(),DocumentCollectionQuestion.id.desc()).limit(max(1,min(int(limit),100))).all()

def create_collection_source_fingerprint(*,collection_id:int,user_id:int)->str:
    c=_find(collection_id,user_id)
    docs=(Document.query.join(DocumentCollectionItem,DocumentCollectionItem.document_id==Document.id).filter(DocumentCollectionItem.collection_id==c.id,current_document_filter()).order_by(Document.id.asc()).all())
    readable=[d for d in docs if str(d.extracted_text or "").strip()]
    if not readable: raise CollectionQuestionNotReadyError("This collection does not have any readable current documents yet.")
    parts=[COLLECTION_QUESTION_WORKFLOW_VERSION,f"collection:{c.id}"]
    for d in readable:
        ch=hashlib.sha256(str(d.extracted_text or "").encode()).hexdigest(); th="|".join(sorted(f"{t.page_number}:{t.table_index}:{t.source_fingerprint}" for t in getattr(d,"tables",[])))
        parts.append(f"document:{d.id}:{d.filename}:{ch}:{th}")
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()

def _sources(r:CollectionRetrievalResult,claims:list[dict[str,Any]]):
    if not claims: raise CollectionQuestionWorkflowError("The answer did not include supported claims.")
    chunks=list(r.chunks); ordered=[]; seen=set(); texts={}
    for i,claim in enumerate(claims,1):
        if not isinstance(claim,dict): raise CollectionQuestionWorkflowError(f"Claim {i} is invalid.")
        text=str(claim.get("text") or "").strip(); ids=claim.get("source_ids")
        if not text or not isinstance(ids,list) or not ids: raise CollectionQuestionWorkflowError(f"Claim {i} did not include a valid source citation.")
        for raw in ids:
            try:sid=int(raw)
            except (TypeError,ValueError) as e: raise CollectionQuestionWorkflowError(f"Claim {i} returned an invalid source citation.") from e
            if sid<1 or sid>len(chunks): raise CollectionQuestionWorkflowError(f"Claim {i} cited a source that was not supplied.")
            texts.setdefault(sid,[]).append(text)
            if sid not in seen: seen.add(sid); ordered.append(sid)
    out=[]
    for sid in ordered:
        src=chunks[sid-1]; trusted=src.source(); preview=build_focused_evidence_preview(str(src.text or "").strip(),question=r.query,claim_text=" ".join(texts.get(sid,[])),matched_terms=tuple(src.matched_terms or ()))
        out.append({"source_id":sid,"document_id":trusted.get("document_id"),"filename":trusted.get("filename"),"chunk_id":trusted.get("chunk_id"),"chunk_index":trusted.get("chunk_index"),"content_type":trusted.get("content_type"),"table_id":trusted.get("table_id"),"page":trusted.get("page"),"section":str(trusted.get("section") or "").strip(),"evidence":preview.text,"preview_type":"focused" if preview.focused else "leading","visibility":"collection_owner"})
    return out

def _answer(claims):
    parts=[]
    for c in claims:
        text=str(c.get("text") or "").strip(); ids=c.get("source_ids") or []; labels=", ".join(f"Source {int(x)}" for x in ids)
        if text and labels: parts.append(f"{text} [{labels}]")
    answer=" ".join(parts).strip()
    if not answer: raise CollectionQuestionWorkflowError("The answer did not contain supported claims.")
    return answer
def _find(cid,uid):
    c=DocumentCollection.query.filter_by(id=cid,user_id=uid).first()
    if c is None: raise CollectionQuestionNotFoundError("Collection not found.")
    return c
def _no_match(q,p,m): return {"success":True,"provider":str(p or "lifeos")[:30],"model":str(m or "collection-answerability")[:100],"question":q,"answer":NO_MATCH_ANSWER,"found_in_document":False,"claims":[]}
def _save_failed(c,uid,q,fp,error):
    try: cfg=get_ai_configuration(); p=str(cfg.get("provider") or "unknown")[:30]; m=str(cfg.get("model") or "unknown")[:100]
    except AIServiceError: p=m="unavailable"
    row=DocumentCollectionQuestion(collection_id=c.id,user_id=uid,question=q,answer=None,sources_json=None,provider=p,model=m,status="Failed",source_fingerprint=fp,error_message=str(error)[:2000])
    try: db.session.add(row); db.session.commit()
    except SQLAlchemyError: db.session.rollback()
