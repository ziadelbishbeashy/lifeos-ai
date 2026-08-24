import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState, type FormEvent } from "react";
import { apiDelete, apiGet, apiPatch, apiPost, ApiError } from "../api/client";
import { EmptyState, ErrorBanner, PageHeader, PageState } from "../components/NativeUi";

type Note = { id:number; project_id:number|null; project:{id:number;title:string}|null; title:string; content:string; note_type:string; is_pinned:boolean; updated_at:string|null; created_at:string|null };
type Project = { id:number; title:string };
type NotesData = { items:Note[]; pinned:Note[]; regular:Note[]; projects:Project[]; note_types:string[]; filters:{q:string;type:string;project:string} };

type NoteInput = { title:string; content:string; note_type:string; project_id:number|null; is_pinned:boolean };

export function NotesPage() {
  const client = useQueryClient();
  const [q,setQ]=useState(""); const [type,setType]=useState("all"); const [project,setProject]=useState("all");
  const [editing,setEditing]=useState<Note|null>(null); const [creating,setCreating]=useState(false); const [error,setError]=useState<string|null>(null);
  const query = useQuery({queryKey:["notes",q,type,project], queryFn:()=>apiGet<NotesData>(`/api/v1/notes?q=${encodeURIComponent(q)}&type=${encodeURIComponent(type)}&project=${encodeURIComponent(project)}`)});
  const refresh=()=>client.invalidateQueries({queryKey:["notes"]});
  const create=useMutation({mutationFn:(input:NoteInput)=>apiPost<{item:Note}>("/api/v1/notes",input),onSuccess:async(r)=>{await refresh();window.location.assign(`/notes/${r.item.id}`)},onError:(e)=>setError(e instanceof ApiError?e.message:"Could not create note.")});
  const update=useMutation({mutationFn:({id,input}:{id:number;input:NoteInput})=>apiPatch<{item:Note}>(`/api/v1/notes/${id}`,input),onSuccess:async()=>{setEditing(null);await refresh()},onError:(e)=>setError(e instanceof ApiError?e.message:"Could not update note.")});
  const pin=useMutation({mutationFn:(id:number)=>apiPost(`/api/v1/notes/${id}/pin`),onSuccess:refresh});
  const del=useMutation({mutationFn:(id:number)=>apiDelete(`/api/v1/notes/${id}`),onSuccess:refresh});
  const items=useMemo(()=>query.data?.items??[],[query.data]);
  if(query.isPending)return <PageState title="Opening Notes" text="Loading your knowledge workspace…"/>;
  if(query.isError||!query.data)return <PageState title="Notes unavailable" text="LifeOS could not load notes." error retry={()=>query.refetch()}/>;
  const data=query.data;
  function submit(event:FormEvent<HTMLFormElement>){event.preventDefault();setError(null);const f=new FormData(event.currentTarget);const input:NoteInput={title:String(f.get("title")||""),content:String(f.get("content")||""),note_type:String(f.get("note_type")||"Quick Note"),project_id:f.get("project_id")?Number(f.get("project_id")):null,is_pinned:f.get("is_pinned")!==null}; editing?update.mutate({id:editing.id,input}):create.mutate(input)}
  return <section className="workspace-page notes-native"><PageHeader eyebrow="Knowledge workspace" title="Notes" description="Capture ideas, project context and AI-assisted understanding without leaving your workspace." actions={<button className="primary-button" onClick={()=>{setCreating(v=>!v);setEditing(null);setError(null)}}>{creating?"Close":"+ New note"}</button>}/>
    <div className="filter-bar panel-card"><label><span>Search</span><input value={q} onChange={e=>setQ(e.target.value)} placeholder="Search notes"/></label><label><span>Type</span><select value={type} onChange={e=>setType(e.target.value)}><option value="all">All types</option>{data.note_types.map(x=><option key={x}>{x}</option>)}</select></label><label><span>Project</span><select value={project} onChange={e=>setProject(e.target.value)}><option value="all">All projects</option>{data.projects.map(x=><option key={x.id} value={x.id}>{x.title}</option>)}</select></label><span className="filter-count">{items.length} notes</span></div>
    {(creating||editing)?<article className="panel-card workspace-editor"><div className="section-heading"><div><span className="panel-kicker">Note editor</span><h2>{editing?"Edit note":"Create note"}</h2></div></div><ErrorBanner message={error}/><form className="native-form-grid" onSubmit={submit}><label>Title<input name="title" defaultValue={editing?.title||""} required/></label><label>Type<select name="note_type" defaultValue={editing?.note_type||"Quick Note"}>{data.note_types.map(x=><option key={x}>{x}</option>)}</select></label><label>Project<select name="project_id" defaultValue={editing?.project_id??""}><option value="">General workspace</option>{data.projects.map(x=><option value={x.id} key={x.id}>{x.title}</option>)}</select></label><label className="check-row"><input type="checkbox" name="is_pinned" defaultChecked={editing?.is_pinned}/><span>Pin note</span></label><label className="full">Content<textarea name="content" rows={9} defaultValue={editing?.content||""} required/></label><div className="form-actions full"><button type="button" className="secondary-button" onClick={()=>{setCreating(false);setEditing(null)}}>Cancel</button><button className="primary-button">{editing?"Save":"Create"}</button></div></form></article>:null}
    <div className="native-card-grid">{items.length?items.map(note=><article className="panel-card note-card-native" key={note.id}><div className="card-topline"><span className="status-pill">{note.note_type}</span>{note.is_pinned?<span title="Pinned">★</span>:null}</div><h3><a href={`/notes/${note.id}`}>{note.title}</a></h3><p>{note.content.slice(0,220)}{note.content.length>220?"…":""}</p><div className="resource-meta"><span>{note.project?.title||"General workspace"}</span><span>{note.updated_at?new Date(note.updated_at).toLocaleDateString():""}</span></div><div className="row-actions"><button className="secondary-button compact" onClick={()=>{setEditing(note);setCreating(false)}}>Edit</button><button className="secondary-button compact" onClick={()=>pin.mutate(note.id)}>{note.is_pinned?"Unpin":"Pin"}</button><button className="danger-button" onClick={()=>{if(confirm(`Delete “${note.title}”?`))del.mutate(note.id)}}>Delete</button></div></article>):<EmptyState title="No notes yet" text="Create a note to start building your knowledge workspace."/>}</div>
  </section>;
}
