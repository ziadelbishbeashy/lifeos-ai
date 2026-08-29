import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../api/client";

type ContextResource = {
  type: string;
  id: number;
  label: string;
  url?: string | null;
  project_title?: string | null;
  detail?: string | null;
};

type ContextConnection = {
  relation_type: string;
  relation_label: string;
  resource: ContextResource;
  reason?: string | null;
  provenance: { type: string; id?: number | null };
};

type ContextPacket = {
  resource: ContextResource;
  summary: string;
  connections: ContextConnection[];
  counts: Record<string, number>;
  context_limited: boolean;
  verified_from_state: boolean;
};

export function ContextConnectionsPanel({ resourceType, resourceId }: { resourceType: string; resourceId: number }) {
  const query = useQuery({
    queryKey: ["context-connections", resourceType, resourceId],
    queryFn: () => apiGet<{ connections: ContextPacket }>(`/api/v1/intelligence/connections/${resourceType}/${resourceId}`),
    enabled: Number.isFinite(resourceId) && resourceId > 0,
  });

  if (query.isPending) {
    return <article className="panel-card context-connections-panel is-loading"><div className="section-heading"><div><span className="panel-kicker">Context graph</span><h2>Connected context</h2></div></div><p>Checking verified workspace relationships…</p></article>;
  }
  if (query.isError || !query.data?.connections) return null;

  const packet = query.data.connections;
  const visible = packet.connections.slice(0, 8);
  return <article className="panel-card context-connections-panel">
    <div className="section-heading">
      <div><span className="panel-kicker">Context graph</span><h2>Connected context</h2><p>{packet.summary}</p></div>
      <span className="success-pill">Verified state</span>
    </div>
    {visible.length ? <div className="context-connections-grid">
      {visible.map((connection) => <div className="context-connection-card" key={`${connection.relation_type}-${connection.resource.type}-${connection.resource.id}`}>
        <div className="context-connection-meta"><span>{connection.relation_label}</span><em>{connection.resource.type.replace("_", " ")}</em></div>
        {connection.resource.url ? <a href={connection.resource.url}>{connection.resource.label}</a> : <strong>{connection.resource.label}</strong>}
        {connection.resource.project_title ? <small>{connection.resource.project_title}</small> : null}
        {connection.reason ? <p>{connection.reason}</p> : null}
        {connection.provenance.type === "ask_lifeos" ? <div className="context-connection-origin">From confirmed Ask LifeOS evidence</div> : null}
      </div>)}
    </div> : <div className="empty-workspace compact-empty"><strong>No explicit connected context yet</strong><span>Project, Module, Collection, and confirmed Ask LifeOS provenance will appear here when they exist.</span></div>}
    {packet.connections.length > visible.length ? <div className="context-connection-footer">Showing {visible.length} of {packet.connections.length} verified connections.</div> : null}
  </article>;
}
