import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { apiGet, apiPatch, apiPost, ApiError } from "../api/client";
import { ErrorBanner, PageHeader, PageState } from "../components/NativeUi";
import type { ProactiveNotification, ProactiveNotificationData } from "../api/types";

type Settings={preferences:Record<string,any>;recent_logs:any[];email_configured:boolean};
const toggles=[['email_enabled','Email notifications'],['task_reminders_enabled','Task reminders'],['custom_task_reminders_enabled','Custom reminders'],['overdue_alerts_enabled','Overdue alerts'],['project_deadline_alerts_enabled','Project deadline alerts'],['project_risk_alerts_enabled','Project risk alerts'],['daily_checkup_enabled','Daily checkup'],['weekly_summary_enabled','Weekly summary'],['monthly_analytics_enabled','Monthly analytics']];
export function NotificationSettingsPage(){const qc=useQueryClient();const [error,setError]=useState<string|null>(null);const [message,setMessage]=useState<string|null>(null);const q=useQuery({queryKey:["notification-settings"],queryFn:()=>apiGet<Settings>("/api/v1/notifications/settings")});const save=useMutation({mutationFn:(x:any)=>apiPatch("/api/v1/notifications/settings",x),onSuccess:async()=>{setMessage("Settings saved.");await qc.invalidateQueries({queryKey:["notification-settings"]})},onError:e=>setError(e instanceof ApiError?e.message:"Could not save settings.")});const action=useMutation({mutationFn:(path:string)=>apiPost<{message:string}>(path),onSuccess:r=>{setMessage(r.message);qc.invalidateQueries({queryKey:["notification-settings"]})},onError:e=>setError(e instanceof ApiError?e.message:"Email action failed.")});if(q.isPending)return <PageState title="Loading notifications" text="Opening your preferences…"/>;if(q.isError||!q.data)return <PageState title="Notifications unavailable" text="Could not load notification settings." error retry={()=>q.refetch()}/>;const d=q.data;
 function submit(e:FormEvent<HTMLFormElement>){e.preventDefault();const f=new FormData(e.currentTarget);const payload:any={};toggles.forEach(([k])=>payload[k]=f.get(k)!==null);for(const k of ['task_reminder_days_before','project_reminder_days_before','daily_checkup_time','weekly_summary_day','weekly_summary_time','monthly_report_day','monthly_report_time','quiet_hours_start','quiet_hours_end'])payload[k]=f.get(k)??'';save.mutate(payload)}
 return <section className="workspace-page"><PageHeader eyebrow="Communication" title="Notification settings" description="Choose which reminders LifeOS may send and when." actions={<a href="/notifications/history" className="secondary-button">History</a>}/><ErrorBanner message={error}/>{message?<div className="form-alert success">{message}</div>:null}{!d.email_configured?<div className="form-alert warning">Email is not configured in the backend environment yet.</div>:null}<form className="panel-card native-settings" onSubmit={submit}><div className="settings-toggle-grid">{toggles.map(([key,label])=><label className="toggle-row" key={key}><span><strong>{label}</strong><small>{key==='email_enabled'?'Master email switch':'Control this notification category'}</small></span><input type="checkbox" name={key} defaultChecked={Boolean(d.preferences[key])}/></label>)}</div><div className="native-form-grid"><label>Task reminder days<input type="number" min="0" max="30" name="task_reminder_days_before" defaultValue={d.preferences.task_reminder_days_before??1}/></label><label>Project reminder days<input type="number" min="0" max="60" name="project_reminder_days_before" defaultValue={d.preferences.project_reminder_days_before??3}/></label><label>Daily time<input type="time" name="daily_checkup_time" defaultValue={String(d.preferences.daily_checkup_time||'08:00').slice(0,5)}/></label><label>Weekly day<input type="number" min="0" max="6" name="weekly_summary_day" defaultValue={d.preferences.weekly_summary_day??6}/></label><label>Weekly time<input type="time" name="weekly_summary_time" defaultValue={String(d.preferences.weekly_summary_time||'18:00').slice(0,5)}/></label><label>Monthly day<input type="number" min="1" max="28" name="monthly_report_day" defaultValue={d.preferences.monthly_report_day??1}/></label><label>Monthly time<input type="time" name="monthly_report_time" defaultValue={String(d.preferences.monthly_report_time||'08:00').slice(0,5)}/></label><label>Quiet hours start<input type="time" name="quiet_hours_start" defaultValue={String(d.preferences.quiet_hours_start||'').slice(0,5)}/></label><label>Quiet hours end<input type="time" name="quiet_hours_end" defaultValue={String(d.preferences.quiet_hours_end||'').slice(0,5)}/></label></div><div className="form-actions"><button className="primary-button">Save preferences</button></div></form><article className="panel-card"><div className="section-heading"><div><span className="panel-kicker">Email tools</span><h2>Run a check now</h2></div></div><div className="hero-actions"><button className="secondary-button" onClick={()=>action.mutate('/api/v1/notifications/email/test')}>Send test email</button><button className="secondary-button" onClick={()=>action.mutate('/api/v1/notifications/email/check')}>Run notification check</button><button className="secondary-button" onClick={()=>action.mutate('/api/v1/notifications/email/daily-summary')}>Daily checkup</button><button className="secondary-button" onClick={()=>action.mutate('/api/v1/notifications/email/weekly-summary')}>Weekly summary</button><button className="secondary-button" onClick={()=>action.mutate('/api/v1/notifications/email/monthly-analytics')}>Monthly analytics</button></div></article></section>}

export function NotificationHistoryPage(){
  const qc=useQueryClient();
  const [error,setError]=useState<string|null>(null);
  const email=useQuery({queryKey:["notification-history"],queryFn:()=>apiGet<{items:any[]}>("/api/v1/notifications/history")});
  const proactive=useQuery({
    queryKey:["lifeos-proactive-notifications"],
    queryFn:()=>apiPost<{proactive:ProactiveNotificationData}>("/api/v1/intelligence/proactive/refresh"),
    refetchInterval:60_000,
    retry:false,
  });
  const noticeAction=useMutation({
    mutationFn:({id,action}:{id:number;action:"read"|"dismiss"})=>apiPost(`/api/v1/intelligence/proactive/${id}/${action}`),
    onSuccess:async()=>{setError(null);await qc.invalidateQueries({queryKey:["lifeos-proactive-notifications"]})},
    onError:e=>setError(e instanceof ApiError?e.message:"Could not update the notification."),
  });
  const readAll=useMutation({
    mutationFn:()=>apiPost<{changed:number}>("/api/v1/intelligence/proactive/read-all"),
    onSuccess:async()=>{setError(null);await qc.invalidateQueries({queryKey:["lifeos-proactive-notifications"]})},
    onError:e=>setError(e instanceof ApiError?e.message:"Could not mark notifications as read."),
  });

  if(email.isPending && proactive.isPending)return <PageState title="Loading notifications" text="Checking what LifeOS noticed…"/>;
  const notices=proactive.data?.proactive.items??[];
  const unread=proactive.data?.proactive.counts.unread??0;

  function openNotice(item:ProactiveNotification){
    if(item.status==="unread") noticeAction.mutate({id:item.id,action:"read"});
  }

  return <section className="workspace-page">
    <PageHeader eyebrow="Proactive intelligence" title="Notifications" description="LifeOS notices meaningful changes and attention signals without waiting for you to ask." actions={<a href="/notifications/settings" className="secondary-button">Settings</a>}/>
    <ErrorBanner message={error}/>

    <article className="panel-card proactive-notification-panel">
      <div className="section-heading"><div><span className="panel-kicker">I15 · In-app</span><h2>LifeOS noticed</h2><p>Generated from verified I14 events. These are suggestions only; LifeOS does not execute workspace actions automatically.</p></div>{unread?<button className="secondary-button compact" type="button" onClick={()=>readAll.mutate()} disabled={readAll.isPending}>Mark all read</button>:null}</div>
      {proactive.isError?<div className="form-alert warning">Proactive intelligence could not refresh. Your existing workspace data is unchanged.</div>:null}
      {notices.length?<div className="proactive-notification-list">{notices.map(item=><div className={`proactive-notification-item severity-${item.severity} ${item.status==="unread"?"is-unread":""}`} key={item.id}>
        <div className="proactive-notification-icon" aria-hidden="true">{item.severity==="high"?"!":item.category==="document_attention"?"D":"L"}</div>
        <div className="proactive-notification-copy"><div className="proactive-notification-topline"><strong>{item.title}</strong><span>{item.status==="unread"?"New":item.status}</span></div><p>{item.message}</p><small>{item.created_at?new Date(item.created_at).toLocaleString():""} · Verified LifeOS state</small></div>
        <div className="proactive-notification-actions">{item.action?.href?<a className="secondary-button compact" href={item.action.href} onClick={()=>openNotice(item)}>{item.action.label||"Open"}</a>:null}{item.status==="unread"?<button className="notification-text-button" type="button" onClick={()=>noticeAction.mutate({id:item.id,action:"read"})}>Mark read</button>:null}<button className="notification-text-button" type="button" onClick={()=>noticeAction.mutate({id:item.id,action:"dismiss"})}>Dismiss</button></div>
      </div>)}</div>:<div className="dashboard-empty-state compact-empty-state"><div className="empty-state-icon">✓</div><h3>Nothing needs your attention</h3><p>LifeOS will surface overdue work, blocked tasks, approaching deadlines, stale document intelligence, and completed analysis here.</p></div>}
    </article>

    <article className="panel-card">
      <div className="section-heading"><div><span className="panel-kicker">Email delivery</span><h2>Email history</h2><p>The existing email reminder system stays separate from I15 in-app intelligence.</p></div></div>
      {email.isError?<div className="form-alert warning">Could not load email history.</div>:email.data?.items?.length?<div className="simple-resource-list">{email.data.items.map(x=><div key={x.id}><strong>{x.subject||x.notification_type}</strong><span>{x.status} · {x.sent_to} · {x.sent_at?new Date(x.sent_at).toLocaleString():''}</span></div>)}</div>:<div className="home-mini-empty">No email notifications have been recorded yet.</div>}
    </article>
  </section>
}
