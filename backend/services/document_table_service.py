"""Structured table extraction for Document Brain (Step 16)."""
from __future__ import annotations
import hashlib, json
from dataclasses import dataclass
from typing import Any
from sqlalchemy.exc import SQLAlchemyError
from database import db
from models import DocumentChunk, DocumentTable
from services.document_access_service import DocumentNotFoundError, require_owned_document
from services.document_chunk_service import DocumentChunkError, rebuild_owned_document_chunks
from storage.base import StorageError, StorageService
from storage.service import get_storage

TABLE_EXTRACTION_VERSION = "document-table-v1"
class DocumentTableError(RuntimeError): pass
class DocumentTableNotFoundError(DocumentTableError): pass

@dataclass(frozen=True)
class ExtractedTable:
    page_number:int; table_index:int; title:str|None; headers:list[str]; rows:list[list[str]]; markdown_text:str; row_count:int; column_count:int

@dataclass(frozen=True)
class DocumentTableExtractionResult:
    document_id:int; tables:list[DocumentTable]; reused_existing:bool; source_fingerprint:str; chunks_rebuilt:bool

def extract_owned_document_tables(*, document_id:int, user_id:int, force:bool=False, rebuild_chunks:bool=True, storage:StorageService|None=None)->DocumentTableExtractionResult:
    try: document=require_owned_document(document_id,user_id)
    except DocumentNotFoundError as e: raise DocumentTableNotFoundError("Document not found.") from e
    storage_service=storage or get_storage()
    try:
        with storage_service.open(document.file_path,"rb") as f: pdf_bytes=f.read()
    except (StorageError,OSError) as e: raise DocumentTableError("LifeOS could not read the PDF for table extraction.") from e
    fingerprint=hashlib.sha256(TABLE_EXTRACTION_VERSION.encode()+b"\n"+pdf_bytes).hexdigest()
    existing=(DocumentTable.query.filter_by(document_id=document.id,user_id=user_id).order_by(DocumentTable.page_number.asc(),DocumentTable.table_index.asc()).all())
    if existing and not force and all(x.source_fingerprint==fingerprint for x in existing):
        return DocumentTableExtractionResult(document.id,existing,True,fingerprint,False)
    extracted=_extract_tables_from_pdf_bytes(pdf_bytes)
    try:
        if existing:
            for chunk in (DocumentChunk.query.filter_by(document_id=document.id,user_id=user_id).filter(DocumentChunk.table_id.isnot(None)).all()): db.session.delete(chunk)
            db.session.flush()
        for row in existing: db.session.delete(row)
        db.session.flush()
        stored=[]
        for t in extracted:
            row=DocumentTable(document_id=document.id,user_id=user_id,page_number=t.page_number,table_index=t.table_index,title=t.title,headers_json=json.dumps(t.headers,ensure_ascii=False),rows_json=json.dumps(t.rows,ensure_ascii=False),markdown_text=t.markdown_text,row_count=t.row_count,column_count=t.column_count,source_fingerprint=fingerprint)
            db.session.add(row); stored.append(row)
        db.session.commit()
    except SQLAlchemyError as e:
        db.session.rollback(); raise DocumentTableError("LifeOS could not save the extracted tables.") from e
    rebuilt=False
    if rebuild_chunks and (str(document.extracted_text or "").strip() or stored):
        try:
            rebuild_owned_document_chunks(document_id=document.id,user_id=user_id)
            rebuilt=True
        except DocumentChunkError as error:
            raise DocumentTableError(
                "Tables were extracted, but LifeOS could not rebuild the searchable document index."
            ) from error
    return DocumentTableExtractionResult(document.id,stored,False,fingerprint,rebuilt)

def list_owned_document_tables(*,document_id:int,user_id:int)->list[DocumentTable]:
    try: document=require_owned_document(document_id,user_id)
    except DocumentNotFoundError as e: raise DocumentTableNotFoundError("Document not found.") from e
    return DocumentTable.query.filter_by(document_id=document.id,user_id=user_id).order_by(DocumentTable.page_number.asc(),DocumentTable.table_index.asc()).all()

def _extract_tables_from_pdf_bytes(pdf_bytes:bytes)->list[ExtractedTable]:
    try: import pymupdf
    except ImportError as e: raise DocumentTableError("PyMuPDF is required for table extraction.") from e
    try: pdf=pymupdf.open(stream=pdf_bytes,filetype="pdf")
    except Exception as e: raise DocumentTableError("LifeOS could not open the PDF for table extraction.") from e
    out=[]
    try:
        for page_index in range(len(pdf)):
            page=pdf[page_index]; fn=getattr(page,"find_tables",None)
            if not callable(fn): continue
            try: found=list(getattr(fn(),"tables",()) or ())
            except Exception: continue
            for table_index,table in enumerate(found,start=1):
                try: raw=table.extract() or []
                except Exception: continue
                rows=_normalize_rows(raw)
                if not rows or max((len(r) for r in rows),default=0)<2: continue
                headers,data=_split_headers(rows); width=max(len(headers),max((len(r) for r in data),default=0))
                if width<2: continue
                headers=_pad_row(headers,width); data=[_pad_row(r,width) for r in data]
                title=_extract_table_title(page,getattr(table,"bbox",None))
                out.append(ExtractedTable(page_index+1,table_index,title,headers,data,_to_markdown(headers,data,title=title),len(data),width))
    finally: pdf.close()
    return out

def _normalize_rows(raw_rows:list[Any])->list[list[str]]:
    out=[]
    for raw in raw_rows:
        if not isinstance(raw,(list,tuple)): continue
        row=[_clean_cell(x) for x in raw]
        if any(row): out.append(row)
    return out

def _clean_cell(v:Any)->str: return " ".join(str(v or "").replace("\n"," ").split()).strip()[:4000]
def _mostly_numeric(t:str)->bool:
    c=t.replace(",","").replace("%","").replace(".","").replace("-",""); return bool(c) and c.isdigit()
def _split_headers(rows:list[list[str]])->tuple[list[str],list[list[str]]]:
    first=rows[0]; non=[c for c in first if c]; width=max(len(r) for r in rows)
    header=len(non)>=2 and len({c.casefold() for c in non})==len(non) and sum(_mostly_numeric(c) for c in non)<=max(1,len(non)//2)
    return (first,rows[1:]) if header else ([f"Column {i}" for i in range(1,width+1)],rows)
def _pad_row(row:list[str],width:int)->list[str]: return (list(row)+[""]*width)[:width]
def _escape_md(v:str)->str: return str(v or "").replace("|","\\|")
def _to_markdown(headers:list[str],rows:list[list[str]],*,title:str|None)->str:
    lines=[]
    if title: lines.append(f"Table: {title}")
    lines += ["| "+" | ".join(_escape_md(x) for x in headers)+" |","| "+" | ".join("---" for _ in headers)+" |"]
    lines += ["| "+" | ".join(_escape_md(x) for x in row)+" |" for row in rows]
    return "\n".join(lines).strip()
def _extract_table_title(page,bbox)->str|None:
    if not bbox: return None
    try:
        import pymupdf
        x0,y0,x1,_=[float(v) for v in bbox]; clip=pymupdf.Rect(x0,max(0.0,y0-90.0),x1,y0); text=str(page.get_text("text",clip=clip) or "").strip()
    except Exception: return None
    lines=[" ".join(x.split()).strip() for x in text.splitlines() if x.strip()]; return lines[-1][:255] if lines else None
