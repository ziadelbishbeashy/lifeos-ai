import { useMemo, useState, type FormEvent } from "react";
import type { Project, ProjectInput } from "../../api/types";

const statuses = ["Planning", "In Progress", "Paused", "Completed"];
const priorities = ["Low", "Medium", "High", "Critical"];
const projectTypes = ["Full-Stack AI System","Web Application","Mobile Application","Machine Learning Project","Graduation Project","Portfolio Project","Research Project","Job Preparation","Other"];

type Props = { initial?: Project | null; submitLabel: string; busy?: boolean; onSubmit:(input:ProjectInput)=>void|Promise<void>; onCancel?:()=>void };

export function ProjectForm({initial,submitLabel,busy,onSubmit,onCancel}:Props){
  const defaults=useMemo<ProjectInput>(()=>({title:initial?.title??"",project_type:initial?.project_type??"",description:initial?.description??"",goal:initial?.goal??"",tech_stack:initial?.tech_stack??"",project_folder:initial?.project_folder??"",github_link:initial?.github_link??"",demo_link:initial?.demo_link??"",start_date:initial?.start_date??"",deadline:initial?.deadline??"",no_deadline:initial?initial.deadline===null:false,status:initial?.status??"In Progress",priority:initial?.priority??"Medium",current_phase:initial?.current_phase??"",progress:initial?.progress??0}),[initial]);
  const [form,setForm]=useState<ProjectInput>(defaults);
  function update<K extends keyof ProjectInput>(key:K,value:ProjectInput[K]){setForm(c=>({...c,[key]:value}))}
  async function submit(e:FormEvent){e.preventDefault();await onSubmit({...form,deadline:form.no_deadline?"":form.deadline})}
  return <form className="professional-project-form" onSubmit={submit}>
    <div className="project-form-grid">
      <div className="project-form-field"><label htmlFor="projectTitle">Project title <span>*</span></label><input id="projectTitle" required maxLength={150} value={form.title} placeholder="Example: LifeOS AI" onChange={e=>update("title",e.target.value)}/></div>
      <div className="project-form-field"><label htmlFor="projectType">Project type</label><select id="projectType" value={form.project_type??""} onChange={e=>update("project_type",e.target.value)}><option value="">Select project type</option>{projectTypes.map(t=><option key={t}>{t}</option>)}</select></div>
      <div className="project-form-field project-form-full"><label htmlFor="projectDescription">Description</label><textarea id="projectDescription" value={form.description??""} placeholder="Describe the project and its main purpose..." onChange={e=>update("description",e.target.value)}/></div>
      <div className="project-form-field project-form-full"><label htmlFor="projectGoal">Main goal</label><textarea id="projectGoal" value={form.goal??""} placeholder="What should this project achieve?" onChange={e=>update("goal",e.target.value)}/></div>
      <div className="project-form-field project-form-full"><label htmlFor="projectStack">Technology stack</label><input id="projectStack" value={form.tech_stack??""} placeholder="Flask, SQL Server, React, AI..." onChange={e=>update("tech_stack",e.target.value)}/></div>
      <div className="project-form-field"><label htmlFor="projectStatus">Status</label><select id="projectStatus" value={form.status} onChange={e=>update("status",e.target.value)}>{statuses.map(x=><option key={x}>{x}</option>)}</select></div>
      <div className="project-form-field"><label htmlFor="projectPriority">Priority</label><select id="projectPriority" value={form.priority} onChange={e=>update("priority",e.target.value)}>{priorities.map(x=><option key={x}>{x}</option>)}</select></div>
      <div className="project-form-field"><label htmlFor="projectStartDate">Start date</label><input id="projectStartDate" type="date" value={form.start_date??""} onChange={e=>update("start_date",e.target.value)}/></div>
      <div className="project-form-field"><label htmlFor="projectDeadline">Deadline</label><input id="projectDeadline" type="date" disabled={!!form.no_deadline} value={form.deadline??""} onChange={e=>update("deadline",e.target.value)}/><label className="professional-checkbox"><input type="checkbox" checked={!!form.no_deadline} onChange={e=>update("no_deadline",e.target.checked)}/><span>No deadline</span></label></div>
      <div className="project-form-field"><label htmlFor="projectPhase">Current phase</label><input id="projectPhase" value={form.current_phase??""} placeholder="Example: Backend development" onChange={e=>update("current_phase",e.target.value)}/></div>
      <div className="project-form-field"><label htmlFor="projectProgress">Progress</label><div className="progress-input-wrapper"><input id="projectProgress" type="number" min={0} max={100} value={form.progress??0} onChange={e=>update("progress",Number(e.target.value))}/><span>%</span></div></div>
      <div className="project-form-divider project-form-full"><span>External Resources</span></div>
      <div className="project-form-field project-form-full"><label htmlFor="projectFolder">Local project folder</label><input id="projectFolder" value={form.project_folder??""} placeholder="C:\\Users\\Name\\Desktop\\project" onChange={e=>update("project_folder",e.target.value)}/></div>
      <div className="project-form-field"><label htmlFor="projectGithub">GitHub repository</label><input id="projectGithub" type="url" value={form.github_link??""} placeholder="https://github.com/username/project" onChange={e=>update("github_link",e.target.value)}/></div>
      <div className="project-form-field"><label htmlFor="projectDemo">Live demo</label><input id="projectDemo" type="url" value={form.demo_link??""} placeholder="https://project-demo.com" onChange={e=>update("demo_link",e.target.value)}/></div>
    </div>
    <div className="project-modal-actions">{onCancel?<button type="button" className="workspace-secondary-button" onClick={onCancel}>Cancel</button>:null}<button type="submit" className="workspace-primary-button" disabled={busy}>{busy?"Saving…":submitLabel}</button></div>
  </form>
}
