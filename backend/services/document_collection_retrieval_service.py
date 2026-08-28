"""Hybrid retrieval across user-defined document collections (Step 17)."""
from __future__ import annotations
import re
from dataclasses import dataclass, replace
from typing import Any
from models import Document, DocumentChunk, DocumentCollection, DocumentCollectionItem
from services.document_chunk_service import DocumentChunkError,DocumentChunkNotFoundError,DocumentChunkNotReadyError,ensure_owned_document_chunks
from services.document_embedding_service import DocumentEmbeddingError,DocumentEmbeddingNotFoundError,DocumentEmbeddingNotReadyError,ensure_owned_document_embeddings,generate_question_embedding
from services.document_hybrid_retrieval_service import HybridRetrievedDocumentChunk,fuse_retrieval_results
from services.document_retrieval_service import rank_document_chunks
from services.document_semantic_retrieval_service import rank_semantic_document_chunks
from services.document_version_service import current_document_filter
DEFAULT_RESULT_LIMIT=10; MAX_RESULT_LIMIT=12; GLOBAL_CANDIDATE_LIMIT=14; MAX_QUERY_CHARACTERS=2000; RETRIEVAL_CONTEXT_CHARACTERS=18000
PAGE_MARKER_PATTERN=re.compile(r"^--- Page\s+\d+\s+---\s*",flags=re.MULTILINE)
class CollectionRetrievalError(RuntimeError): pass
class CollectionRetrievalNotFoundError(CollectionRetrievalError): pass
class CollectionRetrievalNotReadyError(CollectionRetrievalError): pass
class CollectionRetrievalValidationError(CollectionRetrievalError): pass
@dataclass(frozen=True)
class CollectionRetrievedChunk:
    document:Document; retrieved:HybridRetrievedDocumentChunk
    @property
    def chunk(self): return self.retrieved.chunk
    @property
    def matched_terms(self): return self.retrieved.matched_terms
    @property
    def page_start(self): return self.retrieved.page_start
    @property
    def page_end(self): return self.retrieved.page_end
    @property
    def section_title(self): return self.retrieved.section_title
    @property
    def text(self): return self.retrieved.text
    def source(self)->dict[str,Any]:
        b=self.retrieved.source()
        return {"document_id":self.document.id,"filename":self.document.filename,"page":b.get("page"),"section":b.get("section"),"evidence":b.get("evidence"),"chunk_id":self.chunk.id,"chunk_index":self.chunk.chunk_index,"content_type":getattr(self.chunk,"content_type","text") or "text","table_id":getattr(self.chunk,"table_id",None),"visibility":"collection_owner"}
@dataclass(frozen=True)
class CollectionRetrievalResult:
    collection:DocumentCollection; query:str; chunks:list[CollectionRetrievedChunk]; document_count:int; searchable_document_count:int; skipped_document_count:int; mode:str; semantic_error:str|None; chunks_rebuilt_count:int; embedded_count:int; reused_count:int

def retrieve_owned_collection_chunks(*,collection_id:int,user_id:int,query:str,limit:int=DEFAULT_RESULT_LIMIT,force_embeddings:bool=False)->CollectionRetrievalResult:
    q=_clean_query(query); lim=_validate_limit(limit)
    collection=DocumentCollection.query.filter_by(id=collection_id,user_id=user_id).first()
    if collection is None: raise CollectionRetrievalNotFoundError("Collection not found.")
    documents=(Document.query.join(DocumentCollectionItem,DocumentCollectionItem.document_id==Document.id).filter(DocumentCollectionItem.collection_id==collection.id,current_document_filter()).order_by(Document.uploaded_at.desc(),Document.id.desc()).all())
    if not documents: raise CollectionRetrievalNotReadyError("This collection does not contain any current documents yet.")
    searchable=[]; all_chunks=[]; by_id={}; skipped=0; rebuilt_count=0
    for d in documents:
        try: indexed=ensure_owned_document_chunks(document_id=d.id,user_id=user_id)
        except (DocumentChunkNotReadyError,DocumentChunkNotFoundError): skipped+=1; continue
        except DocumentChunkError as e: raise CollectionRetrievalError("LifeOS could not prepare collection documents for search.") from e
        searchable.append(indexed.document); by_id[indexed.document.id]=indexed.document; all_chunks.extend(indexed.chunks); rebuilt_count+=int(bool(indexed.rebuilt))
    if not searchable or not all_chunks: raise CollectionRetrievalNotReadyError("None of the collection documents contains searchable text yet.")
    keyword=rank_document_chunks(query=q,chunks=all_chunks,limit=GLOBAL_CANDIDATE_LIMIT)
    semantic=[]; sem_error=None; embedded_count=0; reused_count=0
    try:
        embedded_chunks=[]; expected=None
        for d in searchable:
            emb=ensure_owned_document_embeddings(document_id=d.id,user_id=user_id,force=force_embeddings)
            cfg=(emb.provider,emb.model,emb.dimensions)
            if expected is None: expected=cfg
            elif cfg!=expected: raise DocumentEmbeddingError("Collection document embeddings use inconsistent configurations.")
            embedded_chunks.extend(emb.chunks); embedded_count+=emb.embedded_count; reused_count+=emb.reused_count; rebuilt_count+=int(bool(emb.chunks_rebuilt))
        qemb,qcfg=generate_question_embedding(question=q); qid=(qcfg.provider,qcfg.model,qcfg.dimensions)
        if expected is not None and qid!=expected: raise DocumentEmbeddingError("The question and collection document embeddings use different configurations.")
        semantic=rank_semantic_document_chunks(question_embedding=qemb,chunks=embedded_chunks,limit=GLOBAL_CANDIDATE_LIMIT)
    except (DocumentEmbeddingNotFoundError,DocumentEmbeddingNotReadyError,DocumentEmbeddingError) as e:
        semantic=[]; sem_error=str(e)
    fused=fuse_retrieval_results(keyword_chunks=keyword,semantic_chunks=semantic,limit=lim)
    wrapped=[CollectionRetrievedChunk(by_id[x.chunk.document_id],x) for x in fused if x.chunk.document_id in by_id]
    return CollectionRetrievalResult(collection,q,wrapped,len(documents),len(searchable),skipped,_mode(len(keyword),len(semantic),sem_error),sem_error,rebuilt_count,embedded_count,reused_count)

def select_collection_sources(*,retrieval_result:CollectionRetrievalResult,source_ids)->CollectionRetrievalResult:
    out=[]; seen=set()
    for raw in source_ids:
        try: sid=int(raw)
        except (TypeError,ValueError): continue
        if sid in seen or sid<1 or sid>len(retrieval_result.chunks): continue
        seen.add(sid); out.append(retrieval_result.chunks[sid-1])
    if not out: raise CollectionRetrievalValidationError("The verifier did not select a valid collection source.")
    return replace(retrieval_result,chunks=out)

def build_collection_context(result:CollectionRetrievalResult,*,max_characters:int=RETRIEVAL_CONTEXT_CHARACTERS)->str:
    if max_characters<500: raise ValueError("Collection retrieval context must allow at least 500 characters.")
    blocks=[]; used=0
    for sid,r in enumerate(result.chunks,start=1):
        loc=[f'Document "{_clean_label(r.document.filename,220)}"']; page=_page_label(r)
        if page: loc.append(f"Page {page}")
        section=_clean_label(r.section_title,220)
        if section: loc.append(section)
        if (getattr(r.chunk,"content_type","text") or "text")=="table": loc.append("Structured table")
        text=PAGE_MARKER_PATTERN.sub("",str(r.text or "")).strip(); block=f"[Source {sid} | {' | '.join(loc)}]\n{text}"; sep=2 if blocks else 0; remain=max_characters-used-sep
        if remain<=0: break
        if len(block)>remain:
            if remain<200: break
            block=block[:remain-3].rstrip()+"..."
        blocks.append(block); used+=len(block)+sep
    return "\n\n".join(blocks)
def _page_label(r):
    if r.page_start and r.page_end and r.page_start!=r.page_end: return f"{r.page_start}-{r.page_end}"
    p=r.page_start or r.page_end; return str(p) if p else ""
def _mode(k,s,e):
    if e:return "keyword_fallback"
    if k and s:return "hybrid"
    if s:return "semantic_only"
    return "keyword_only"
def _clean_query(q):
    c=" ".join(str(q or "").split()).strip()
    if not c: raise CollectionRetrievalValidationError("Please enter a collection question.")
    if len(c)>MAX_QUERY_CHARACTERS: raise CollectionRetrievalValidationError(f"The collection question cannot exceed {MAX_QUERY_CHARACTERS:,} characters.")
    return c
def _validate_limit(v):
    try:c=int(v)
    except (TypeError,ValueError) as e: raise CollectionRetrievalValidationError("The result limit must be a number.") from e
    if c<1 or c>MAX_RESULT_LIMIT: raise CollectionRetrievalValidationError(f"The result limit must be between 1 and {MAX_RESULT_LIMIT}.")
    return c
def _clean_label(v,n): return " ".join(str(v or "").split()).strip()[:n]
