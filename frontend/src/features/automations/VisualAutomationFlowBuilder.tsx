import { useEffect, useMemo, useRef, useState } from "react";
import type {
  AutomationActionType,
  AutomationRegistryData,
  AutomationTriggerType,
  AutomationVisualGraph,
  AutomationVisualNodeId,
  LifeOSAutomation,
  ProjectListData,
} from "../../api/types";

const CANVAS_WIDTH = 980;
const CANVAS_HEIGHT = 430;
const NODE_WIDTH = 228;
const NODE_HEIGHT = 142;

const DEFAULT_POSITIONS: Record<AutomationVisualNodeId, { x: number; y: number }> = {
  trigger: { x: 60, y: 145 },
  intelligence: { x: 376, y: 145 },
  delivery: { x: 692, y: 145 },
};

const FIXED_EDGES: AutomationVisualGraph["edges"] = [
  { id: "trigger-intelligence", source: "trigger", target: "intelligence" },
  { id: "intelligence-delivery", source: "intelligence", target: "delivery" },
];

type PositionMap = Record<AutomationVisualNodeId, { x: number; y: number }>;

type Props = {
  registry: AutomationRegistryData;
  projects: ProjectListData["items"];
  automation?: LifeOSAutomation | null;
  timezone: string;
  busy?: boolean;
  onCancel: () => void;
  onSave: (payload: Record<string, unknown>) => void;
};

function cleanPositions(graph?: AutomationVisualGraph): PositionMap {
  const next: PositionMap = {
    trigger: { ...DEFAULT_POSITIONS.trigger },
    intelligence: { ...DEFAULT_POSITIONS.intelligence },
    delivery: { ...DEFAULT_POSITIONS.delivery },
  };
  for (const node of graph?.nodes ?? []) {
    if (node.id in next && Number.isFinite(node.position?.x) && Number.isFinite(node.position?.y)) {
      next[node.id] = { x: node.position.x, y: node.position.y };
    }
  }
  return next;
}

function actionTitle(registry: AutomationRegistryData, type: string) {
  return registry.actions.find((item) => item.type === type)?.label ?? type.replace(/_/g, " ");
}

function triggerTitle(registry: AutomationRegistryData, type: string) {
  return registry.triggers.find((item) => item.type === type)?.label ?? type.replace(/_/g, " ");
}

function eventTitle(value: string) {
  return value.replace(/\./g, " · ");
}

function FlowEdge({ source, target, positions }: { source: AutomationVisualNodeId; target: AutomationVisualNodeId; positions: PositionMap }) {
  const from = positions[source];
  const to = positions[target];
  const x1 = from.x + NODE_WIDTH;
  const y1 = from.y + NODE_HEIGHT / 2;
  const x2 = to.x;
  const y2 = to.y + NODE_HEIGHT / 2;
  const bend = Math.max(58, Math.abs(x2 - x1) * 0.42);
  const d = `M ${x1} ${y1} C ${x1 + bend} ${y1}, ${x2 - bend} ${y2}, ${x2} ${y2}`;
  return <path className="visual-flow-edge" d={d} />;
}

function FlowNode({
  id,
  positions,
  selected,
  title,
  detail,
  kicker,
  icon,
  onSelect,
  onDragStart,
}: {
  id: AutomationVisualNodeId;
  positions: PositionMap;
  selected: boolean;
  title: string;
  detail: string;
  kicker: string;
  icon: string;
  onSelect: () => void;
  onDragStart: (event: React.PointerEvent<HTMLDivElement>) => void;
}) {
  const position = positions[id];
  return <div
    className={`visual-flow-node visual-flow-node-${id} ${selected ? "selected" : ""}`}
    style={{ left: position.x, top: position.y }}
    onClick={onSelect}
  >
    <div className="visual-flow-node-drag" onPointerDown={onDragStart} title="Drag node">
      <span className="visual-flow-node-icon">{icon}</span>
      <span className="visual-flow-node-kicker">{kicker}</span>
      <span className="visual-flow-node-grip">⠿</span>
    </div>
    <strong>{title}</strong>
    <p>{detail}</p>
    {id !== "trigger" ? <span className="visual-flow-handle input" /> : null}
    {id !== "delivery" ? <span className="visual-flow-handle output" /> : null}
  </div>;
}

export function VisualAutomationFlowBuilder({ registry, projects, automation, timezone, busy = false, onCancel, onSave }: Props) {
  const [name, setName] = useState(automation?.name ?? "My intelligence flow");
  const [description, setDescription] = useState(automation?.description ?? "Built visually with LifeOS Flow Studio.");
  const [triggerType, setTriggerType] = useState<AutomationTriggerType>(automation?.trigger.type ?? "schedule_daily");
  const [eventType, setEventType] = useState(String(automation?.trigger.config.event_type ?? "task.overdue"));
  const [hour, setHour] = useState(Number(automation?.trigger.config.hour ?? 8));
  const [minute, setMinute] = useState(Number(automation?.trigger.config.minute ?? 0));
  const [weekday, setWeekday] = useState(Number(automation?.trigger.config.weekday ?? 0));
  const [actionType, setActionType] = useState<AutomationActionType>(automation?.action.type ?? "today_briefing");
  const [projectId, setProjectId] = useState(String(automation?.action.config.project_id ?? ""));
  const [selectedNode, setSelectedNode] = useState<AutomationVisualNodeId>("trigger");
  const [positions, setPositions] = useState<PositionMap>(() => cleanPositions(automation?.visual_graph));
  const [dragging, setDragging] = useState<{ id: AutomationVisualNodeId; dx: number; dy: number } | null>(null);
  const canvasRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!dragging) return;
    const move = (event: PointerEvent) => {
      const rect = canvasRef.current?.getBoundingClientRect();
      if (!rect) return;
      const x = Math.min(CANVAS_WIDTH - NODE_WIDTH - 24, Math.max(24, event.clientX - rect.left - dragging.dx));
      const y = Math.min(CANVAS_HEIGHT - NODE_HEIGHT - 24, Math.max(24, event.clientY - rect.top - dragging.dy));
      setPositions((current) => ({ ...current, [dragging.id]: { x: Math.round(x), y: Math.round(y) } }));
    };
    const stop = () => setDragging(null);
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop, { once: true });
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
    };
  }, [dragging]);

  const triggerDetail = useMemo(() => {
    if (triggerType === "event") return eventTitle(eventType);
    const hh = String(hour).padStart(2, "0");
    const mm = String(minute).padStart(2, "0");
    if (triggerType === "schedule_weekly") {
      return `${["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][weekday] ?? "Weekly"} · ${hh}:${mm}`;
    }
    return `Every day · ${hh}:${mm}`;
  }, [eventType, hour, minute, triggerType, weekday]);

  const selectedAction = registry.actions.find((item) => item.type === actionType);
  const actionDetail = actionType === "project_review"
    ? `${projects.find((item) => String(item.id) === projectId)?.title ?? "Choose project"} · verified review`
    : selectedAction?.description ?? "Verified LifeOS intelligence";

  function beginDrag(id: AutomationVisualNodeId, event: React.PointerEvent<HTMLDivElement>) {
    event.preventDefault();
    event.stopPropagation();
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    const pos = positions[id];
    setSelectedNode(id);
    setDragging({ id, dx: event.clientX - rect.left - pos.x, dy: event.clientY - rect.top - pos.y });
  }

  function resetLayout() {
    setPositions({
      trigger: { ...DEFAULT_POSITIONS.trigger },
      intelligence: { ...DEFAULT_POSITIONS.intelligence },
      delivery: { ...DEFAULT_POSITIONS.delivery },
    });
  }

  function save() {
    const triggerConfig = triggerType === "event"
      ? { event_type: eventType }
      : triggerType === "schedule_weekly"
        ? { weekday, hour, minute }
        : { hour, minute };
    const actionConfig = actionType === "project_review" ? { project_id: Number(projectId) } : {};
    const visualGraph: AutomationVisualGraph = {
      version: registry.visual_flow.version,
      nodes: (["trigger", "intelligence", "delivery"] as AutomationVisualNodeId[]).map((id) => ({
        id,
        kind: id,
        position: positions[id],
      })),
      edges: FIXED_EDGES,
    };
    onSave({
      name: name.trim(),
      description: description.trim(),
      trigger_type: triggerType,
      trigger_config: triggerConfig,
      action_type: actionType,
      action_config: actionConfig,
      timezone,
      visual_graph: visualGraph,
      ...(automation ? {} : { enabled: false }),
    });
  }

  const invalid = !name.trim() || (actionType === "project_review" && !projectId);

  return <section className="visual-flow-studio panel-card">
    <div className="visual-flow-studio-head">
      <div>
        <span className="panel-kicker">I18 · Visual Flow Studio</span>
        <h2>{automation ? `Edit ${automation.name}` : "Build an intelligence automation"}</h2>
        <p>Arrange the flow visually. The canvas compiles back to the same reviewed I17 engine — it cannot add arbitrary code or bypass I9.</p>
      </div>
      <div className="visual-flow-head-actions">
        <button type="button" className="secondary-button" onClick={resetLayout}>Reset layout</button>
        <button type="button" className="secondary-button" onClick={onCancel}>Close</button>
        <button type="button" className="primary-button" disabled={busy || invalid} onClick={save}>{busy ? "Saving…" : automation ? "Save flow" : "Create flow"}</button>
      </div>
    </div>

    <div className="visual-flow-name-row">
      <label className="field-label">Flow name<input value={name} maxLength={160} onChange={(event) => setName(event.target.value)} /></label>
      <label className="field-label">Description<input value={description} maxLength={400} onChange={(event) => setDescription(event.target.value)} /></label>
      <label className="field-label">Timezone<input value={timezone} readOnly /></label>
    </div>

    <div className="visual-flow-workbench">
      <aside className="visual-flow-palette">
        <span className="panel-kicker">Nodes</span>
        <button type="button" className={selectedNode === "trigger" ? "active" : ""} onClick={() => setSelectedNode("trigger")}><span>⏱</span><div><strong>Trigger</strong><small>When the flow starts</small></div></button>
        <button type="button" className={selectedNode === "intelligence" ? "active" : ""} onClick={() => setSelectedNode("intelligence")}><span>✦</span><div><strong>Intelligence</strong><small>What LifeOS analyzes</small></div></button>
        <button type="button" className={selectedNode === "delivery" ? "active" : ""} onClick={() => setSelectedNode("delivery")}><span>🔔</span><div><strong>Notify</strong><small>Safe in-app delivery</small></div></button>
        <div className="visual-flow-palette-note"><strong>V1 guardrail</strong><p>Connections are intentionally fixed. Future workspace-changing nodes will be placed behind the I9 confirmation boundary.</p></div>
      </aside>

      <div className="visual-flow-canvas-scroll">
        <div className="visual-flow-canvas" ref={canvasRef} style={{ width: CANVAS_WIDTH, height: CANVAS_HEIGHT }}>
          <div className="visual-flow-grid" />
          <svg className="visual-flow-edges" viewBox={`0 0 ${CANVAS_WIDTH} ${CANVAS_HEIGHT}`} preserveAspectRatio="none" aria-hidden="true">
            <FlowEdge source="trigger" target="intelligence" positions={positions} />
            <FlowEdge source="intelligence" target="delivery" positions={positions} />
          </svg>
          <FlowNode id="trigger" positions={positions} selected={selectedNode === "trigger"} kicker="TRIGGER" icon="⏱" title={triggerTitle(registry, triggerType)} detail={triggerDetail} onSelect={() => setSelectedNode("trigger")} onDragStart={(event) => beginDrag("trigger", event)} />
          <FlowNode id="intelligence" positions={positions} selected={selectedNode === "intelligence"} kicker="LIFEOS INTELLIGENCE" icon="✦" title={actionTitle(registry, actionType)} detail={actionDetail} onSelect={() => setSelectedNode("intelligence")} onDragStart={(event) => beginDrag("intelligence", event)} />
          <FlowNode id="delivery" positions={positions} selected={selectedNode === "delivery"} kicker="DELIVERY" icon="🔔" title="In-app notification" detail="Verified result delivered through I14 → I15." onSelect={() => setSelectedNode("delivery")} onDragStart={(event) => beginDrag("delivery", event)} />
        </div>
      </div>

      <aside className="visual-flow-inspector">
        <span className="panel-kicker">Configure node</span>
        {selectedNode === "trigger" ? <>
          <h3>Trigger</h3>
          <p>Choose when this automation becomes eligible to run.</p>
          <label className="field-label">Trigger type<select value={triggerType} onChange={(event) => setTriggerType(event.target.value as AutomationTriggerType)}>{registry.triggers.map((item) => <option value={item.type} key={item.type}>{item.label}</option>)}</select></label>
          {triggerType === "event" ? <label className="field-label">LifeOS event<select value={eventType} onChange={(event) => setEventType(event.target.value)}>{registry.event_types.map((item) => <option value={item} key={item}>{eventTitle(item)}</option>)}</select></label> : <>
            {triggerType === "schedule_weekly" ? <label className="field-label">Weekday<select value={weekday} onChange={(event) => setWeekday(Number(event.target.value))}>{["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"].map((item, index) => <option value={index} key={item}>{item}</option>)}</select></label> : null}
            <div className="visual-flow-time-grid"><label className="field-label">Hour<input type="number" min={0} max={23} value={hour} onChange={(event) => setHour(Number(event.target.value))} /></label><label className="field-label">Minute<input type="number" min={0} max={59} value={minute} onChange={(event) => setMinute(Number(event.target.value))} /></label></div>
          </>}
        </> : null}
        {selectedNode === "intelligence" ? <>
          <h3>LifeOS Intelligence</h3>
          <p>Select one reviewed intelligence workflow. No arbitrary prompts or code are executed from the canvas.</p>
          <label className="field-label">Intelligence action<select value={actionType} onChange={(event) => setActionType(event.target.value as AutomationActionType)}>{registry.actions.map((item) => <option value={item.type} key={item.type}>{item.label}</option>)}</select></label>
          {actionType === "project_review" ? <label className="field-label">Project<select value={projectId} onChange={(event) => setProjectId(event.target.value)}><option value="">Choose project</option>{projects.map((project) => <option value={project.id} key={project.id}>{project.title}</option>)}</select></label> : null}
          <div className="visual-flow-inspector-description">{selectedAction?.description}</div>
        </> : null}
        {selectedNode === "delivery" ? <>
          <h3>Notify me</h3>
          <p>Successful automation results are normalized into I14 and materialized through I15 as an in-app LifeOS notification.</p>
          <div className="visual-flow-locked-field"><span>Delivery</span><strong>In-app notification</strong><small>Locked for I18 V1</small></div>
          <div className="visual-flow-locked-field"><span>Workspace mutation</span><strong>Off</strong><small>I9 confirmation remains required</small></div>
        </> : null}
      </aside>
    </div>

    <div className="visual-flow-contract">
      <span>✓ Persisted layout</span><span>✓ I17 execution engine</span><span>✓ I14 event boundary</span><span>✓ I15 delivery</span><span>✓ I9 protects workspace writes</span>
    </div>
  </section>;
}
