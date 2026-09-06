import { useEffect, useMemo, useRef, useState } from "react";
import type {
  AutomationRegistryData,
  AutomationRun,
  AutomationVisualGraph,
  AutomationVisualNode,
  AutomationVisualNodeCategory,
  AutomationVisualNodeDefinition,
  AutomationVisualTemplate,
  DocumentCollectionSummary,
  DocumentSummary,
  LearningModule,
  LifeOSAutomation,
  ProjectListData,
} from "../../api/types";

const BASE_CANVAS_WIDTH = 1120;
const CANVAS_HEIGHT = 560;
const NODE_WIDTH = 236;
const NODE_HEIGHT = 148;
const LAYOUT_GAP = 292;

const CATEGORY_DEFAULTS: Record<string, { x: number; y: number }> = {
  trigger: { x: 60, y: 190 },
  context: { x: 330, y: 190 },
  intelligence: { x: 600, y: 190 },
  condition: { x: 860, y: 190 },
  output: { x: 1120, y: 190 },
  proposal: { x: 1380, y: 190 },
};

const ICONS: Record<string, string> = {
  clock: "⏱", calendar: "◫", alert: "!", deadline: "⌛", document: "▤", version: "↻",
  blocked: "⊘", project: "◆", play: "▶", workspace: "⌂", module: "▦", collection: "▥",
  activity: "≋", spark: "✦", review: "◎", risk: "△", find: "⌕", event: "◇", rank: "⇅",
  bell: "●", save: "▣", suggest: "→", task: "✓", note: "≡", refresh: "↻", filter: "◇",
};

type Props = {
  registry: AutomationRegistryData;
  projects: ProjectListData["items"];
  documents: DocumentSummary[];
  modules: LearningModule[];
  collections: DocumentCollectionSummary[];
  automation?: LifeOSAutomation | null;
  latestRun?: AutomationRun | null;
  timezone: string;
  busy?: boolean;
  onCancel: () => void;
  onSave: (payload: Record<string, unknown>) => void;
};

type DragState = { id: string; dx: number; dy: number } | null;

type LinearGraph = {
  order: string[];
  indegree: Map<string, number>;
  outgoing: Map<string, string[]>;
};

function definitionMap(registry: AutomationRegistryData) {
  return new Map(registry.visual_flow.nodes.map((item) => [item.type, item]));
}

function cloneGraph(graph?: AutomationVisualGraph): { nodes: AutomationVisualNode[]; edges: AutomationVisualGraph["edges"] } {
  if (!graph) return { nodes: [], edges: [] };
  return {
    nodes: graph.nodes.map((node) => ({ ...node, position: { ...node.position }, config: { ...(node.config ?? {}) } })),
    edges: graph.edges.map((edge) => ({ ...edge })),
  };
}

function newNodeId(category: string, nodes: AutomationVisualNode[]) {
  let counter = 1;
  const ids = new Set(nodes.map((node) => node.id));
  while (ids.has(`${category}-${counter}`)) counter += 1;
  return `${category}-${counter}`;
}

function defaultConfig(definition: AutomationVisualNodeDefinition): Record<string, unknown> {
  if (definition.category === "trigger") {
    const triggerType = String(definition.binding.trigger_type ?? "");
    if (triggerType === "schedule_weekly") return { weekday: 0, hour: 8, minute: 0 };
    if (triggerType === "schedule_daily") return { hour: 8, minute: 0 };
    if (triggerType === "event") return { event_type: String(definition.binding.event_type ?? "") };
  }
  if (["context.project", "context.document", "context.module", "context.collection"].includes(definition.type)) {
    return { scope_mode: "selected" };
  }
  if (definition.type === "context.recent_activity") return { window: "week" };
  if (definition.type === "intelligence.ask_lifeos") return { instruction: "" };
  if (definition.type === "condition.attention_needed") return { minimum_attention: "medium" };
  return {};
}

function iconFor(definition?: AutomationVisualNodeDefinition) {
  return ICONS[definition?.icon ?? ""] ?? "•";
}

function graphHasCycle(nodes: AutomationVisualNode[], edges: AutomationVisualGraph["edges"]) {
  const ids = new Set(nodes.map((node) => node.id));
  const indegree = new Map<string, number>();
  const outgoing = new Map<string, string[]>();
  for (const id of ids) { indegree.set(id, 0); outgoing.set(id, []); }
  for (const edge of edges) {
    if (!ids.has(edge.source) || !ids.has(edge.target)) continue;
    outgoing.get(edge.source)?.push(edge.target);
    indegree.set(edge.target, (indegree.get(edge.target) ?? 0) + 1);
  }
  const queue = [...ids].filter((id) => (indegree.get(id) ?? 0) === 0);
  let visited = 0;
  while (queue.length) {
    const id = queue.pop()!;
    visited += 1;
    for (const target of outgoing.get(id) ?? []) {
      const next = (indegree.get(target) ?? 0) - 1;
      indegree.set(target, next);
      if (next === 0) queue.push(target);
    }
  }
  return visited !== ids.size;
}

function linearGraph(nodes: AutomationVisualNode[], edges: AutomationVisualGraph["edges"]): LinearGraph | null {
  if (!nodes.length) return null;
  const ids = new Set(nodes.map((node) => node.id));
  const indegree = new Map<string, number>();
  const outgoing = new Map<string, string[]>();
  for (const id of ids) { indegree.set(id, 0); outgoing.set(id, []); }
  for (const edge of edges) {
    if (!ids.has(edge.source) || !ids.has(edge.target)) return null;
    outgoing.get(edge.source)!.push(edge.target);
    indegree.set(edge.target, (indegree.get(edge.target) ?? 0) + 1);
  }
  if ([...indegree.values()].some((value) => value > 1) || [...outgoing.values()].some((value) => value.length > 1)) return null;
  const roots = [...ids].filter((id) => (indegree.get(id) ?? 0) === 0);
  if (roots.length !== 1) return null;
  const order: string[] = [];
  const seen = new Set<string>();
  let current: string | undefined = roots[0];
  while (current) {
    if (seen.has(current)) return null;
    seen.add(current);
    order.push(current);
    current = outgoing.get(current)?.[0];
  }
  if (order.length !== nodes.length) return null;
  return { order, indegree, outgoing };
}

function edgePath(source: AutomationVisualNode, target: AutomationVisualNode) {
  const x1 = source.position.x + NODE_WIDTH;
  const y1 = source.position.y + NODE_HEIGHT / 2;
  const x2 = target.position.x;
  const y2 = target.position.y + NODE_HEIGHT / 2;
  const bend = Math.max(72, Math.abs(x2 - x1) * 0.42);
  return `M ${x1} ${y1} C ${x1 + bend} ${y1}, ${x2 - bend} ${y2}, ${x2} ${y2}`;
}

function categoryName(value: AutomationVisualNodeCategory) {
  if (value === "trigger") return "When";
  if (value === "context") return "Look at";
  if (value === "intelligence") return "Ask LifeOS to";
  if (value === "condition") return "Only continue if";
  if (value === "output") return "Then";
  if (value === "proposal") return "Then · ask me first";
  return value;
}

function categoryHelp(value: AutomationVisualNodeCategory) {
  if (value === "trigger") return "Choose when this automation should start.";
  if (value === "context") return "Choose the information LifeOS is allowed to use.";
  if (value === "intelligence") return "Choose what you want LifeOS to figure out.";
  if (value === "condition") return "Optional: stop quietly when the previous result does not need action.";
  if (value === "output") return "Choose what should happen with the result.";
  if (value === "proposal") return "LifeOS can suggest a change, but you still confirm it.";
  return "Approved LifeOS step.";
}

const FRIENDLY_NODE_LABELS: Record<string, string> = {
  "trigger.schedule_daily": "Every day",
  "trigger.schedule_weekly": "Every week",
  "trigger.manual_run": "When I click Run now",
  "trigger.task_overdue": "When a task becomes overdue",
  "trigger.deadline_approaching": "When a deadline is approaching",
  "trigger.task_blocked": "When a task becomes blocked",
  "trigger.project_overdue": "When a project becomes overdue",
  "trigger.project_deadline_approaching": "When a project deadline is approaching",
  "trigger.document_stale": "When a document becomes stale",
  "trigger.document_version_changed": "When a document changes",
  "context.all_lifeos": "All of LifeOS",
  "context.project": "A project",
  "context.document": "A document",
  "context.module": "A module",
  "context.collection": "A collection",
  "context.recent_activity": "Recent activity",
  "intelligence.today_briefing": "Build my daily briefing",
  "intelligence.portfolio_review": "Review my workspace",
  "intelligence.project_review": "Review a project",
  "intelligence.review_document": "Review the knowledge",
  "intelligence.rank_priorities": "Rank what matters most",
  "intelligence.detect_risks": "Find important risks",
  "intelligence.what_changed": "Tell me what changed",
  "intelligence.find_unhandled_findings": "Find things I have not handled",
  "intelligence.event_context_review": "Understand what happened",
  "intelligence.ask_lifeos": "Ask LifeOS my own question",
  "condition.attention_needed": "Something needs attention",
  "condition.results_found": "Results were actually found",
  "output.notify_me": "Notify me",
  "output.save_review_result": "Save the result in run history",
  "output.suggest_action": "Suggest what I should do next",
  "proposal.create_task": "Ask me before creating a task",
  "proposal.save_note": "Ask me before saving a note",
  "proposal.refresh_analysis": "Ask me before refreshing the analysis",
};

function friendlyNodeLabel(definition?: AutomationVisualNodeDefinition) {
  if (!definition) return "LifeOS step";
  return FRIENDLY_NODE_LABELS[definition.type] ?? definition.label;
}

function phaseAvailable(definition?: AutomationVisualNodeDefinition) {
  return definition?.availability === "i18_1" || definition?.availability === "i18_2" || definition?.availability === "i18_3" || definition?.availability === "i18_6";
}

export function VisualAutomationFlowBuilder({
  registry,
  projects,
  documents,
  modules,
  collections,
  automation,
  latestRun,
  timezone,
  busy = false,
  onCancel,
  onSave,
}: Props) {
  const initial = useMemo(() => cloneGraph(automation?.visual_graph), [automation]);
  const definitions = useMemo(() => definitionMap(registry), [registry]);
  const [name, setName] = useState(automation?.name ?? "My intelligence flow");
  const [description, setDescription] = useState(automation?.description ?? "Built visually with LifeOS Flow Studio.");
  const [flowTimezone] = useState(automation?.timezone ?? timezone);
  const [nodes, setNodes] = useState<AutomationVisualNode[]>(initial.nodes);
  const [edges, setEdges] = useState<AutomationVisualGraph["edges"]>(initial.edges);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(initial.nodes[0]?.id ?? null);
  const [dragging, setDragging] = useState<DragState>(null);
  const [pendingSource, setPendingSource] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(automation?.visual_graph.validation?.valid === false ? automation.visual_graph.validation.error ?? "This saved flow needs repair." : null);
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const canvasWidth = Math.max(BASE_CANVAS_WIDTH, nodes.length * LAYOUT_GAP + 120);

  const selectedNode = nodes.find((node) => node.id === selectedNodeId) ?? null;
  const selectedDefinition = selectedNode ? definitions.get(selectedNode.type) : undefined;
  const graphShape = useMemo(() => linearGraph(nodes, edges), [nodes, edges]);
  const orderedNodes = useMemo(() => {
    if (!graphShape) return nodes;
    const map = new Map(nodes.map((node) => [node.id, node]));
    return graphShape.order.map((id) => map.get(id)!).filter(Boolean);
  }, [graphShape, nodes]);
  const triggerNode = orderedNodes.find((node) => node.category === "trigger") ?? nodes.find((node) => node.category === "trigger") ?? null;
  const triggerDefinition = triggerNode ? definitions.get(triggerNode.type) : undefined;
  const selectedProjectContext = orderedNodes.find((node) => node.type === "context.project" && String(node.config?.scope_mode ?? "selected") === "selected" && Number(node.config?.project_id)) ?? null;
  const anchorNode = orderedNodes.find((node) => node.category === "intelligence" && Boolean(definitions.get(node.type)?.binding.action_type)) ?? null;
  const anchorDefinition = anchorNode ? definitions.get(anchorNode.type) : undefined;
  const compiledVisualDraft = nodes.length !== 3
    || nodes.some((node) => definitions.get(node.type)?.availability !== "i18_1")
    || nodes.find((node) => node.category === "output")?.type !== "output.notify_me";

  useEffect(() => {
    if (!dragging) return;
    const move = (event: PointerEvent) => {
      const rect = canvasRef.current?.getBoundingClientRect();
      if (!rect) return;
      const x = Math.min(canvasWidth - NODE_WIDTH - 26, Math.max(26, event.clientX - rect.left - dragging.dx));
      const y = Math.min(CANVAS_HEIGHT - NODE_HEIGHT - 26, Math.max(26, event.clientY - rect.top - dragging.dy));
      setNodes((current) => current.map((node) => node.id === dragging.id
        ? { ...node, position: { x: Math.round(x), y: Math.round(y) } }
        : node));
    };
    const stop = () => setDragging(null);
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop, { once: true });
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
    };
  }, [canvasWidth, dragging]);

  const validationIssues = useMemo(() => {
    const issues: string[] = [];
    const constraints = registry.visual_flow.constraints;
    const hasNormalThen = nodes.some((node) => node.category === "output");
    const hasApprovalThen = nodes.some((node) => node.category === "proposal");
    for (const category of constraints.required_categories) {
      const count = nodes.filter((node) => node.category === category).length;
      if (category === "output" && hasApprovalThen) continue;
      if (count === 0) issues.push(`Add at least one ${categoryName(category)} node.`);
    }
    if (!hasNormalThen && !hasApprovalThen) issues.push("Finish with a THEN step or a THEN · ASK ME FIRST step.");
    for (const [category, maximum] of Object.entries(constraints.max_per_category)) {
      const count = nodes.filter((node) => node.category === category).length;
      if (count > maximum) issues.push(`You can add at most ${maximum} ${categoryName(category)} step${maximum === 1 ? "" : "s"}.`);
    }
    if (nodes.length > constraints.max_nodes) issues.push(`This automation can contain at most ${constraints.max_nodes} steps.`);
    if (nodes.some((node) => !phaseAvailable(definitions.get(node.type)))) issues.push("One step is not available yet. Remove it or choose another step.");
    if (new Set(nodes.map((node) => node.id)).size !== nodes.length) issues.push("Two steps have the same internal ID. Remove one of them and add it again.");

    const nodeIds = new Set(nodes.map((node) => node.id));
    if (edges.some((edge) => !nodeIds.has(edge.source) || !nodeIds.has(edge.target))) issues.push("One connection points to a step that was removed. Reconnect the flow.");
    if (edges.some((edge) => {
      const source = nodes.find((node) => node.id === edge.source);
      const target = nodes.find((node) => node.id === edge.target);
      return source && target && !registry.visual_flow.connection_rules.some((rule) => rule.source === source.category && rule.target === target.category);
    })) issues.push("One connection is out of order. Keep the flow moving from WHEN toward THEN.");
    if (graphHasCycle(nodes, edges)) issues.push("A step cannot loop back to an earlier step. Keep the automation moving forward.");
    if (nodes.length && edges.length !== nodes.length - 1) issues.push("Connect every step into one continuous line.");
    if (nodes.length && !graphShape) issues.push("For now, one automation follows one path. Remove branches and keep a single line of steps.");

    if (graphShape) {
      const byId = new Map(nodes.map((node) => [node.id, node]));
      const ordered = graphShape.order.map((id) => byId.get(id)!).filter(Boolean);
      if (ordered[0]?.category !== "trigger") issues.push("Start the automation with a WHEN step.");
      const outputIndex = ordered.findIndex((node) => node.category === "output");
      if (outputIndex >= 0 && ordered.slice(outputIndex + 1).some((node) => node.category === "context" || node.category === "intelligence")) {
        issues.push("LOOK AT and ASK LIFEOS TO steps must come before THEN.");
      }
      const proposal = ordered.find((node) => node.category === "proposal");
      if (proposal) {
        if (ordered[ordered.length - 1]?.id !== proposal.id) issues.push("A change that needs your approval must be the final step.");
        const proposalIndex = ordered.findIndex((node) => node.id === proposal.id);
        const previous = proposalIndex > 0 ? ordered[proposalIndex - 1] : null;
        if (!previous || !["intelligence", "condition", "output"].includes(previous.category)) {
          issues.push("Put ASK ME FIRST after an AI step or an optional condition.");
        } else if (previous.category === "output" && previous.type !== "output.suggest_action") {
          issues.push("ASK ME FIRST can follow an AI/condition step directly, or follow “Suggest what I should do next”.");
        }
      }
      const reviewDocumentIndex = ordered.findIndex((node) => node.type === "intelligence.review_document");
      if (reviewDocumentIndex >= 0 && !ordered.slice(0, reviewDocumentIndex).some((node) => ["context.document", "context.collection", "context.module"].includes(node.type))) {
        issues.push("Before reviewing knowledge, add a document, collection, or module in LOOK AT.");
      }
    }

    if (!anchorNode) issues.push("Add at least one ASK LIFEOS TO step that performs the main analysis.");

    const triggerType = String(triggerDefinition?.binding.trigger_type ?? "");
    if (triggerNode && (triggerType === "schedule_daily" || triggerType === "schedule_weekly")) {
      const hour = Number(triggerNode.config?.hour ?? 8);
      const minute = Number(triggerNode.config?.minute ?? 0);
      if (!Number.isInteger(hour) || hour < 0 || hour > 23) issues.push("Schedule hour must be between 0 and 23.");
      if (!Number.isInteger(minute) || minute < 0 || minute > 59) issues.push("Schedule minute must be between 0 and 59.");
      if (triggerType === "schedule_weekly") {
        const weekday = Number(triggerNode.config?.weekday ?? 0);
        if (!Number.isInteger(weekday) || weekday < 0 || weekday > 6) issues.push("Choose a valid weekday.");
      }
    }

    for (const node of nodes) {
      if (node.type === "intelligence.project_review" && !Number(node.config?.project_id) && !Number(selectedProjectContext?.config?.project_id)) issues.push("Choose which project LifeOS should review, or add that project in LOOK AT.");
      if (node.type === "context.project") {
        const mode = String(node.config?.scope_mode ?? "selected");
        if (mode === "selected" && !Number(node.config?.project_id)) issues.push("Choose a project in the LOOK AT step.");
        if (mode === "trigger" && triggerType !== "event") issues.push("A project can come from an event only when the automation starts from an event.");
      }
      if (node.type === "context.document") {
        const mode = String(node.config?.scope_mode ?? "selected");
        if (mode === "selected" && !Number(node.config?.document_id)) issues.push("Choose a document in the LOOK AT step.");
        const eventType = String(triggerDefinition?.binding.event_type ?? "");
        if (mode === "trigger" && !(triggerType === "event" && ["document.intelligence_stale", "document.version_changed"].includes(eventType))) {
          issues.push("A document can come from the event only for document-stale or document-changed automations.");
        }
      }
      if (node.type === "context.module" && !Number(node.config?.module_id)) issues.push("Choose a module in the LOOK AT step.");
      if (node.type === "context.collection" && !Number(node.config?.collection_id)) issues.push("Choose a collection in the LOOK AT step.");
      if (node.type === "intelligence.ask_lifeos") {
        const instruction = String(node.config?.instruction ?? "").trim();
        if (instruction.length < 3) issues.push("Write what you want LifeOS to figure out in the custom AI step.");
        if (instruction.length > 600) issues.push("Keep the custom LifeOS instruction under 600 characters.");
      }
      if (node.type === "condition.attention_needed" && !["medium", "high", "critical"].includes(String(node.config?.minimum_attention ?? "medium"))) {
        issues.push("Choose a valid attention level for the condition.");
      }
    }
    return [...new Set(issues)];
  }, [anchorNode, definitions, edges, graphShape, nodes, registry.visual_flow.connection_rules, registry.visual_flow.constraints, selectedProjectContext, triggerDefinition, triggerNode]);

  function placeDefinition(definition: AutomationVisualNodeDefinition, position?: { x: number; y: number }) {
    if (!phaseAvailable(definition)) {
      setNotice(`${friendlyNodeLabel(definition)} is not available yet.`);
      return;
    }
    const maximum = Number(registry.visual_flow.constraints.max_per_category[definition.category] ?? registry.visual_flow.constraints.max_nodes);
    const sameCategory = nodes.filter((node) => node.category === definition.category);
    if (maximum === 1 && sameCategory[0]) {
      const existing = sameCategory[0];
      setNodes((current) => current.map((node) => node.id === existing.id ? {
        ...node,
        type: definition.type,
        config: defaultConfig(definition),
        ...(position ? { position } : {}),
      } : node));
      setSelectedNodeId(existing.id);
      setNotice(`Changed the ${categoryName(definition.category)} step to ${friendlyNodeLabel(definition)}.`);
      return;
    }
    if (sameCategory.length >= maximum || nodes.length >= registry.visual_flow.constraints.max_nodes) {
      setNotice(`You can add at most ${maximum} ${categoryName(definition.category)} step${maximum === 1 ? "" : "s"}.`);
      return;
    }
    const id = newNodeId(definition.category, nodes);
    const tailId = graphShape?.order[graphShape.order.length - 1];
    const tail = tailId ? nodes.find((node) => node.id === tailId) : null;
    const canAppend = Boolean(tail && registry.visual_flow.connection_rules.some((rule) => rule.source === tail.category && rule.target === definition.category));
    const fallback = canAppend
      ? { x: 56 + nodes.length * LAYOUT_GAP, y: 190 }
      : CATEGORY_DEFAULTS[definition.category] ?? { x: 420, y: 190 };
    const next: AutomationVisualNode = {
      id,
      type: definition.type,
      category: definition.category,
      position: position ?? fallback,
      config: defaultConfig(definition),
    };
    setNodes((current) => [...current, next]);
    if (tail && canAppend) {
      const edgeId = `edge-${tail.id}-${id}`.slice(0, 64);
      setEdges((current) => [...current, { id: edgeId, source: tail.id, target: id }]);
      setNotice(`Added ${friendlyNodeLabel(definition)} and connected it to the previous step.`);
    } else {
      setNotice(nodes.length ? `Added ${friendlyNodeLabel(definition)}. Connect it to the flow when you are ready.` : `Great — now add what LifeOS should look at or think about.`);
    }
    setSelectedNodeId(id);
  }

  function paletteDragStart(event: React.DragEvent<HTMLButtonElement>, definition: AutomationVisualNodeDefinition) {
    event.dataTransfer.effectAllowed = phaseAvailable(definition) ? "copy" : "none";
    event.dataTransfer.setData("application/x-lifeos-node", definition.type);
  }

  function dropOnCanvas(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault();
    const nodeType = event.dataTransfer.getData("application/x-lifeos-node");
    const definition = definitions.get(nodeType);
    if (!definition) return;
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    const position = {
      x: Math.min(canvasWidth - NODE_WIDTH - 26, Math.max(26, Math.round(event.clientX - rect.left - NODE_WIDTH / 2))),
      y: Math.min(CANVAS_HEIGHT - NODE_HEIGHT - 26, Math.max(26, Math.round(event.clientY - rect.top - NODE_HEIGHT / 2))),
    };
    placeDefinition(definition, position);
  }

  function beginNodeDrag(node: AutomationVisualNode, event: React.PointerEvent<HTMLDivElement>) {
    event.preventDefault();
    event.stopPropagation();
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    setSelectedNodeId(node.id);
    setDragging({ id: node.id, dx: event.clientX - rect.left - node.position.x, dy: event.clientY - rect.top - node.position.y });
  }

  function connectTo(targetId: string) {
    if (!pendingSource || pendingSource === targetId) { setPendingSource(null); return; }
    const source = nodes.find((node) => node.id === pendingSource);
    const target = nodes.find((node) => node.id === targetId);
    if (!source || !target) { setPendingSource(null); return; }
    const allowed = registry.visual_flow.connection_rules.some((rule) => rule.source === source.category && rule.target === target.category);
    if (!allowed) {
      setNotice(`That connection is out of order. Keep the automation moving from WHEN toward THEN.`);
      setPendingSource(null);
      return;
    }
    const id = `edge-${source.id}-${target.id}`.slice(0, 64);
    setEdges((current) => [
      ...current.filter((edge) => edge.source !== source.id && edge.target !== target.id),
      { id, source: source.id, target: target.id },
    ]);
    setPendingSource(null);
    setNotice(null);
  }

  function removeNode(id: string) {
    setNodes((current) => current.filter((node) => node.id !== id));
    setEdges((current) => current.filter((edge) => edge.source !== id && edge.target !== id));
    setSelectedNodeId(null);
    setPendingSource((current) => current === id ? null : current);
  }

  function updateSelectedConfig(patch: Record<string, unknown>) {
    if (!selectedNode) return;
    setNodes((current) => current.map((node) => node.id === selectedNode.id
      ? { ...node, config: { ...(node.config ?? {}), ...patch } }
      : node));
  }

  function resetLayout() {
    const shape = linearGraph(nodes, edges);
    const order = shape?.order ?? nodes.map((node) => node.id);
    const indexById = new Map(order.map((id, index) => [id, index]));
    setNodes((current) => current.map((node) => ({
      ...node,
      position: { x: 56 + (indexById.get(node.id) ?? 0) * LAYOUT_GAP, y: 190 },
    })));
  }

  function save() {
    if (validationIssues.length || !triggerNode || !triggerDefinition || !anchorNode || !anchorDefinition) return;
    const triggerType = String(triggerDefinition.binding.trigger_type ?? "");
    const actionType = String(anchorDefinition.binding.action_type ?? "");

    let triggerConfig: Record<string, unknown> = {};
    if (triggerType === "event") {
      triggerConfig = { event_type: String(triggerDefinition.binding.event_type ?? triggerNode.config?.event_type ?? "") };
    } else if (triggerType === "manual") {
      triggerConfig = {};
    } else if (triggerType === "schedule_weekly") {
      triggerConfig = {
        weekday: Number(triggerNode.config?.weekday ?? 0),
        hour: Number(triggerNode.config?.hour ?? 8),
        minute: Number(triggerNode.config?.minute ?? 0),
      };
    } else {
      triggerConfig = { hour: Number(triggerNode.config?.hour ?? 8), minute: Number(triggerNode.config?.minute ?? 0) };
    }
    const actionConfig = actionType === "project_review"
      ? { project_id: Number(anchorNode.config?.project_id ?? selectedProjectContext?.config?.project_id) }
      : actionType === "custom_ask"
        ? { instruction: String(anchorNode.config?.instruction ?? "").trim() }
        : {};
    const visualGraph: AutomationVisualGraph = {
      version: registry.visual_flow.version,
      phase: registry.visual_flow.phase,
      nodes: nodes.map((node) => ({
        id: node.id,
        type: node.type,
        category: node.category,
        position: { x: Math.round(node.position.x), y: Math.round(node.position.y) },
        config: { ...(node.config ?? {}) },
      })),
      edges: edges.map((edge) => ({ ...edge })),
    };
    onSave({
      name: name.trim(),
      description: description.trim(),
      trigger_type: triggerType,
      trigger_config: triggerConfig,
      action_type: actionType,
      action_config: actionConfig,
      timezone: flowTimezone,
      visual_graph: visualGraph,
      ...(automation ? {} : { enabled: false }),
    });
  }

  const grouped = registry.visual_flow.categories.map((category) => ({
    ...category,
    label: categoryName(category.id),
    description: categoryHelp(category.id),
    nodes: registry.visual_flow.nodes.filter((node) => node.category === category.id),
  })).filter((category) => category.nodes.length > 0);

  const triggerIsEvent = String(triggerDefinition?.binding.trigger_type ?? "") === "event";
  const triggerEventType = String(triggerDefinition?.binding.event_type ?? "");
  const triggerProvidesDocument = triggerIsEvent && ["document.intelligence_stale", "document.version_changed"].includes(triggerEventType);
  const savedPlan = automation?.compiled_plan;
  const latestVisualFlow = latestRun?.output
    ? (typeof latestRun.output.visual_flow === "object" && latestRun.output.visual_flow !== null
      ? latestRun.output.visual_flow as { status?: string; node_runs?: Array<Record<string, unknown>>; error?: string }
      : Array.isArray(latestRun.output.flow_trace)
        ? { status: latestRun.status, node_runs: latestRun.output.flow_trace as Array<Record<string, unknown>>, error: String(latestRun.output.halt_reason ?? "") || undefined }
        : null)
    : null;
  const latestNodeRuns = new Map((latestVisualFlow?.node_runs ?? []).map((run) => [String(run.node_id ?? ""), run]));

  function applyStarterTemplate(template: AutomationVisualTemplate) {
    const graph = cloneGraph(template.visual_graph);
    setName(template.name);
    setDescription(template.description);
    setNodes(graph.nodes);
    setEdges(graph.edges);
    setSelectedNodeId(graph.nodes[0]?.id ?? null);
    setPendingSource(null);
    setNotice(`Loaded “${template.name}”. Change any step, then save when it reads the way you want.`);
  }

  const plainEnglishSummary = useMemo(() => {
    if (!orderedNodes.length) return "Choose a recipe below, or build from left to right: When → Look at → Ask LifeOS to → Then.";
    const weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
    const trigger = orderedNodes.find((node) => node.category === "trigger");
    const triggerDef = trigger ? definitions.get(trigger.type) : undefined;
    let when = triggerDef ? friendlyNodeLabel(triggerDef) : "When the automation starts";
    if (trigger && triggerDef?.binding.trigger_type === "schedule_daily") {
      when = `Every day at ${String(Number(trigger.config?.hour ?? 8)).padStart(2, "0")}:${String(Number(trigger.config?.minute ?? 0)).padStart(2, "0")}`;
    } else if (trigger && triggerDef?.binding.trigger_type === "schedule_weekly") {
      const day = weekdays[Number(trigger.config?.weekday ?? 0)] ?? "week";
      when = `Every ${day} at ${String(Number(trigger.config?.hour ?? 8)).padStart(2, "0")}:${String(Number(trigger.config?.minute ?? 0)).padStart(2, "0")}`;
    }

    const contextNames = orderedNodes.filter((node) => node.category === "context").map((node) => {
      if (node.type === "context.all_lifeos") return "my LifeOS workspace";
      if (node.type === "context.recent_activity") return String(node.config?.window ?? "week") === "today" ? "today’s recent activity" : "recent activity from this week";
      if (node.type === "context.project") {
        if (String(node.config?.scope_mode ?? "selected") === "trigger") return "the project from that event";
        return projects.find((item) => item.id === Number(node.config?.project_id))?.title ?? "a selected project";
      }
      if (node.type === "context.document") {
        if (String(node.config?.scope_mode ?? "selected") === "trigger") return "the document from that event";
        return documents.find((item) => item.id === Number(node.config?.document_id))?.filename ?? "a selected document";
      }
      if (node.type === "context.module") return modules.find((item) => item.id === Number(node.config?.module_id))?.title ?? "a selected module";
      if (node.type === "context.collection") return collections.find((item) => item.id === Number(node.config?.collection_id))?.name ?? "a selected collection";
      return friendlyNodeLabel(definitions.get(node.type));
    });
    const thinking = orderedNodes.filter((node) => node.category === "intelligence").map((node) => {
      if (node.type === "intelligence.ask_lifeos") return `answer “${String(node.config?.instruction ?? "my question").trim() || "my question"}”`;
      return friendlyNodeLabel(definitions.get(node.type)).replace(/^./, (value) => value.toLowerCase());
    });
    const conditions = orderedNodes.filter((node) => node.category === "condition").map((node) => {
      if (node.type === "condition.attention_needed") return `only continue if the result needs ${String(node.config?.minimum_attention ?? "medium")} attention or higher`;
      return "only continue if useful results were found";
    });
    const results = orderedNodes.filter((node) => node.category === "output" || node.category === "proposal").map((node) => friendlyNodeLabel(definitions.get(node.type)).replace(/^./, (value) => value.toLowerCase()));

    let sentence = when;
    if (contextNames.length) sentence += `, look at ${contextNames.join(" and ")}`;
    if (thinking.length) sentence += `, ask LifeOS to ${thinking.join(", then ")}`;
    if (conditions.length) sentence += `, ${conditions.join(", then ")}`;
    if (results.length) sentence += `, then ${results.join(", then ")}`;
    return `${sentence}.`;
  }, [collections, definitions, documents, modules, orderedNodes, projects]);

  return <section className="visual-flow-studio panel-card">
    <div className="visual-flow-studio-head">
      <div>
        <span className="panel-kicker">Visual automation builder</span>
        <h2>{automation ? `Edit ${automation.name}` : "Tell LifeOS what should happen automatically"}</h2>
        <p>Build the sentence from left to right: choose <strong>when</strong> it starts, <strong>what LifeOS should look at</strong>, <strong>what it should figure out</strong>, and <strong>what happens with the result</strong>.</p>
      </div>
      <div className="visual-flow-head-actions">
        <button type="button" className="secondary-button" onClick={resetLayout}>Arrange steps</button>
        <button type="button" className="secondary-button" onClick={onCancel}>Close</button>
        <button type="button" className="primary-button" disabled={busy || !name.trim() || validationIssues.length > 0} onClick={save}>{busy ? "Saving…" : automation ? "Save automation" : "Create automation"}</button>
      </div>
    </div>

    <div className="visual-flow-name-row">
      <label className="field-label">Automation name<input value={name} maxLength={160} onChange={(event) => setName(event.target.value)} /></label>
      <label className="field-label">What is this for?<input value={description} maxLength={400} onChange={(event) => setDescription(event.target.value)} /></label>
      <label className="field-label">Your timezone<input value={flowTimezone} readOnly /></label>
    </div>

    <div className="visual-flow-howto" aria-label="How a LifeOS automation works">
      <div><span>1</span><strong>WHEN</strong><small>When should it start?</small></div>
      <b>→</b>
      <div><span>2</span><strong>LOOK AT</strong><small>What information should it use?</small></div>
      <b>→</b>
      <div><span>3</span><strong>ASK LIFEOS TO</strong><small>What should AI figure out?</small></div>
      <b>→</b>
      <div><span>4</span><strong>THEN</strong><small>What should happen next?</small></div>
    </div>
    <div className="visual-flow-optional-gate"><strong>Optional smart gate:</strong><span>Add “ONLY CONTINUE IF” after an AI step when you only want a notification or proposal if something important was actually found.</span></div>

    {!automation && (registry.visual_templates ?? []).length ? <div className="visual-flow-starter-strip">
      <div><span className="panel-kicker">Not sure where to start?</span><strong>Start with a ready-made recipe</strong><small>You can change every step before saving.</small></div>
      <div className="visual-flow-starter-buttons">{(registry.visual_templates ?? []).slice(0, 4).map((template) => <button type="button" className="secondary-button" key={template.key} onClick={() => applyStarterTemplate(template)}>{template.name}</button>)}</div>
    </div> : null}

    <div className="visual-flow-plain-summary">
      <span>In plain English</span>
      <strong>{plainEnglishSummary}</strong>
    </div>

    {notice ? <div className="visual-flow-inline-notice">{notice}</div> : null}
    <div className={`visual-flow-compile-banner ${validationIssues.length ? "compiler-only" : "direct"}`}>
      <div><strong>{validationIssues.length ? "Finish the flow before saving" : "LifeOS understands this flow"}</strong><span>{validationIssues.length ? "The panel on the right shows what still needs attention." : "When saved, LifeOS validates the steps again on the backend before anything can run."}</span></div>
      <details className="visual-flow-technical-details"><summary>Technical details</summary><small>{savedPlan ? `Execution plan ${savedPlan.plan_id} · ${savedPlan.steps.length} steps · ${compiledVisualDraft ? "compiled visual" : "direct-compatible"}` : `${nodes.length} draft steps · backend compiler validates on save`}</small></details>
    </div>

    {latestRun ? <div className={`visual-flow-last-run ${latestRun.status}`}>
      <strong>Latest {latestRun.dry_run ? "preview" : "run"} · {latestRun.status}</strong>
      <span>{latestRun.error_message || (latestVisualFlow?.status === "succeeded" ? `${latestVisualFlow.node_runs?.length ?? 0} steps completed. Open run history if you want to see each step.` : "Open run history to see what happened step by step.")}</span>
    </div> : null}

    <div className="visual-flow-workbench">
      <aside className="visual-flow-palette">
        <div className="visual-flow-palette-heading"><span className="panel-kicker">Add a step</span><small>Click in order · LifeOS connects steps automatically</small></div>
        {grouped.map((group) => <div className="visual-flow-palette-group" key={group.id}>
          <div className="visual-flow-palette-group-title"><strong>{group.label}</strong><small>{group.description}</small></div>
          {group.nodes.map((definition) => {
            const available = phaseAvailable(definition);
            const compilerNode = definition.availability !== "i18_1";
            return <button
              type="button"
              className={`visual-flow-palette-node ${available ? "" : "future"} ${compilerNode ? "compiler" : ""}`}
              key={definition.type}
              draggable={available}
              onDragStart={(event) => paletteDragStart(event, definition)}
              onClick={() => placeDefinition(definition)}
              title={definition.description}
            >
              <span className="visual-flow-palette-icon">{iconFor(definition)}</span>
              <span><strong>{friendlyNodeLabel(definition)}</strong><small>{available ? categoryHelp(definition.category) : "Not available yet"}</small></span>
              {definition.category === "proposal" ? <em>ASK FIRST</em> : null}
            </button>;
          })}
        </div>)}
        <div className="visual-flow-palette-note"><strong>Safe by design</strong><p>LifeOS can analyze and notify automatically. If a step would change your workspace, it can only suggest the change and ask you to confirm it first.</p></div>
      </aside>

      <div className="visual-flow-canvas-scroll">
        <div
          className={`visual-flow-canvas ${pendingSource ? "connecting" : ""}`}
          ref={canvasRef}
          style={{ width: canvasWidth, height: CANVAS_HEIGHT }}
          onDragOver={(event) => { event.preventDefault(); event.dataTransfer.dropEffect = "copy"; }}
          onDrop={dropOnCanvas}
          onClick={() => setSelectedNodeId(null)}
        >
          <div className="visual-flow-grid" />
          {nodes.length === 0 ? <div className="visual-flow-canvas-empty"><span>✦</span><strong>Build from left to right</strong><p>Start with WHEN, then add what to LOOK AT, what to ASK LIFEOS TO do, and what happens THEN.</p></div> : null}
          <svg className="visual-flow-edges" viewBox={`0 0 ${canvasWidth} ${CANVAS_HEIGHT}`} preserveAspectRatio="none" aria-hidden="true">
            {edges.map((edge) => {
              const source = nodes.find((node) => node.id === edge.source);
              const target = nodes.find((node) => node.id === edge.target);
              if (!source || !target) return null;
              return <path key={edge.id} className="visual-flow-edge" d={edgePath(source, target)} />;
            })}
          </svg>
          {nodes.map((node) => {
            const definition = definitions.get(node.type);
            const selected = selectedNodeId === node.id;
            const canInput = registry.visual_flow.connection_rules.some((rule) => rule.target === node.category);
            const canOutput = registry.visual_flow.connection_rules.some((rule) => rule.source === node.category);
            const latestNodeRun = latestNodeRuns.get(node.id);
            const latestStatus = String(latestNodeRun?.status ?? "");
            return <article
              key={node.id}
              className={`visual-flow-node visual-flow-node-${node.category} ${selected ? "selected" : ""} ${definition?.availability !== "i18_1" ? "compiler-node" : ""} ${latestStatus ? `run-${latestStatus}` : ""}`}
              style={{ left: node.position.x, top: node.position.y }}
              onClick={(event) => { event.stopPropagation(); setSelectedNodeId(node.id); }}
            >
              <div className="visual-flow-node-drag" onPointerDown={(event) => beginNodeDrag(node, event)} title="Drag node">
                <span className="visual-flow-node-icon">{iconFor(definition)}</span>
                <span className="visual-flow-node-kicker">{categoryName(node.category)}</span>
                <span className="visual-flow-node-grip">⠿</span>
              </div>
              <strong>{friendlyNodeLabel(definition)}</strong>
              <p>{categoryHelp(node.category)}</p>
              {latestStatus ? <span className={`visual-flow-node-run-badge ${latestStatus}`}>{latestStatus}{typeof latestNodeRun?.duration_ms === "number" ? ` · ${latestNodeRun.duration_ms}ms` : ""}</span> : null}
              {canInput ? <button type="button" className="visual-flow-handle input" title="Connect the previous step here" onClick={(event) => { event.stopPropagation(); connectTo(node.id); }} /> : null}
              {canOutput ? <button type="button" className={`visual-flow-handle output ${pendingSource === node.id ? "pending" : ""}`} title="Connect this step to the next one" onClick={(event) => { event.stopPropagation(); setPendingSource((current) => current === node.id ? null : node.id); }} /> : null}
            </article>;
          })}
        </div>
      </div>

      <aside className="visual-flow-inspector">
        <span className="panel-kicker">Set up this step</span>
        {!selectedNode || !selectedDefinition ? <div className="visual-flow-inspector-empty"><strong>Select a step</strong><p>Click any box on the canvas. LifeOS will show only the settings that matter for that step.</p></div> : <>
          <div className="visual-flow-inspector-title"><span>{iconFor(selectedDefinition)}</span><div><h3>{friendlyNodeLabel(selectedDefinition)}</h3><p>{categoryName(selectedDefinition.category)}</p></div></div>
          <p>{categoryHelp(selectedDefinition.category)}</p>

          {selectedDefinition.category === "trigger" && selectedDefinition.binding.trigger_type === "schedule_daily" ? <div className="visual-flow-time-grid">
            <label className="field-label">Hour<input type="number" min={0} max={23} value={Number(selectedNode.config?.hour ?? 8)} onChange={(event) => updateSelectedConfig({ hour: Number(event.target.value) })} /></label>
            <label className="field-label">Minute<input type="number" min={0} max={59} value={Number(selectedNode.config?.minute ?? 0)} onChange={(event) => updateSelectedConfig({ minute: Number(event.target.value) })} /></label>
          </div> : null}

          {selectedDefinition.category === "trigger" && selectedDefinition.binding.trigger_type === "schedule_weekly" ? <>
            <label className="field-label">Weekday<select value={Number(selectedNode.config?.weekday ?? 0)} onChange={(event) => updateSelectedConfig({ weekday: Number(event.target.value) })}>{["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"].map((item, index) => <option value={index} key={item}>{item}</option>)}</select></label>
            <div className="visual-flow-time-grid">
              <label className="field-label">Hour<input type="number" min={0} max={23} value={Number(selectedNode.config?.hour ?? 8)} onChange={(event) => updateSelectedConfig({ hour: Number(event.target.value) })} /></label>
              <label className="field-label">Minute<input type="number" min={0} max={59} value={Number(selectedNode.config?.minute ?? 0)} onChange={(event) => updateSelectedConfig({ minute: Number(event.target.value) })} /></label>
            </div>
          </> : null}

          {selectedDefinition.category === "trigger" && selectedDefinition.binding.trigger_type === "event" ? <div className="visual-flow-locked-field"><span>Starts when</span><strong>{friendlyNodeLabel(selectedDefinition)}</strong><small>LifeOS verifies the event before the flow uses it.</small></div> : null}

          {selectedDefinition.category === "trigger" && selectedDefinition.binding.trigger_type === "manual" ? <div className="visual-flow-locked-field"><span>Starts when</span><strong>You click Run now</strong><small>This automation will not run by itself in the background.</small></div> : null}

          {selectedDefinition.type === "context.project" ? <>
            <label className="field-label">Which project?<select value={String(selectedNode.config?.scope_mode ?? "selected")} onChange={(event) => updateSelectedConfig({ scope_mode: event.target.value })}><option value="selected">Choose a project</option><option value="trigger" disabled={!triggerIsEvent}>Use the project from the event</option></select></label>
            {String(selectedNode.config?.scope_mode ?? "selected") === "selected" ? <label className="field-label">Project<select value={String(selectedNode.config?.project_id ?? "")} onChange={(event) => updateSelectedConfig({ project_id: Number(event.target.value) })}><option value="">Choose project</option>{projects.map((project) => <option value={project.id} key={project.id}>{project.title}</option>)}</select></label> : null}
          </> : null}

          {selectedDefinition.type === "context.document" ? <>
            <label className="field-label">Which document?<select value={String(selectedNode.config?.scope_mode ?? "selected")} onChange={(event) => updateSelectedConfig({ scope_mode: event.target.value })}><option value="selected">Choose a document</option><option value="trigger" disabled={!triggerProvidesDocument}>Use the document from the event</option></select></label>
            {String(selectedNode.config?.scope_mode ?? "selected") === "selected" ? <label className="field-label">Document<select value={String(selectedNode.config?.document_id ?? "")} onChange={(event) => updateSelectedConfig({ document_id: Number(event.target.value) })}><option value="">Choose document</option>{documents.map((document) => <option value={document.id} key={document.id}>{document.filename}</option>)}</select></label> : <div className="visual-flow-locked-field"><span>Document intelligence</span><strong>Uses Document Brain</strong><small>LifeOS keeps retrieval evidence with the result.</small></div>}
          </> : null}

          {selectedDefinition.type === "context.module" ? <label className="field-label">Module<select value={String(selectedNode.config?.module_id ?? "")} onChange={(event) => updateSelectedConfig({ module_id: Number(event.target.value), scope_mode: "selected" })}><option value="">Choose module</option>{modules.map((module) => <option value={module.id} key={module.id}>{module.title}</option>)}</select></label> : null}

          {selectedDefinition.type === "context.collection" ? <label className="field-label">Collection<select value={String(selectedNode.config?.collection_id ?? "")} onChange={(event) => updateSelectedConfig({ collection_id: Number(event.target.value), scope_mode: "selected" })}><option value="">Choose collection</option>{collections.map((collection) => <option value={collection.id} key={collection.id}>{collection.name}</option>)}</select></label> : null}

          {selectedDefinition.type === "context.recent_activity" ? <label className="field-label">Activity window<select value={String(selectedNode.config?.window ?? "week")} onChange={(event) => updateSelectedConfig({ window: event.target.value })}><option value="today">Today</option><option value="week">This week</option></select></label> : null}

          {selectedDefinition.binding.action_type === "project_review" ? (selectedProjectContext ? <div className="visual-flow-locked-field"><span>Project</span><strong>{projects.find((project) => project.id === Number(selectedProjectContext.config?.project_id))?.title ?? "Selected project"}</strong><small>LifeOS reuses the project you already chose in LOOK AT, so you do not have to select it twice.</small></div> : <label className="field-label">Project<select value={String(selectedNode.config?.project_id ?? "")} onChange={(event) => updateSelectedConfig({ project_id: Number(event.target.value) })}><option value="">Choose project</option>{projects.map((project) => <option value={project.id} key={project.id}>{project.title}</option>)}</select></label>) : null}

          {selectedDefinition.type === "intelligence.review_document" ? <div className="visual-flow-locked-field"><span>Knowledge source</span><strong>Document Brain</strong><small>The answer stays grounded in the selected document, collection, or module.</small></div> : null}

          {selectedDefinition.type === "intelligence.ask_lifeos" ? <>
            <label className="field-label">What should LifeOS figure out?<textarea rows={5} maxLength={600} value={String(selectedNode.config?.instruction ?? "")} onChange={(event) => updateSelectedConfig({ instruction: event.target.value })} placeholder="Example: Based on this project, what is most likely to block me this week?" /></label>
            <div className="visual-flow-locked-field"><span>Speed</span><strong>Common project risk questions use fast verified intelligence</strong><small>LifeOS reuses its project risk/prioritization engine when it can. Truly open-ended questions may call the AI provider and take longer.</small></div>
            <div className="visual-flow-locked-field"><span>Safety</span><strong>Read-only Ask LifeOS</strong><small>This question uses the selected verified context. It cannot run arbitrary tools or change the workspace.</small></div>
          </> : null}

          {selectedDefinition.type === "condition.attention_needed" ? <>
            <label className="field-label">Continue only when attention is at least<select value={String(selectedNode.config?.minimum_attention ?? "medium")} onChange={(event) => updateSelectedConfig({ minimum_attention: event.target.value })}><option value="medium">Medium</option><option value="high">High</option><option value="critical">Critical</option></select></label>
            <div className="visual-flow-locked-field"><span>If the condition is false</span><strong>End quietly</strong><small>Later steps are marked skipped. No notification or proposal is created.</small></div>
          </> : null}

          {selectedDefinition.type === "condition.results_found" ? <div className="visual-flow-locked-field"><span>Continue when</span><strong>The previous step found useful results</strong><small>If there are no findings, priorities, activity items, sources, or usable answer, the run ends quietly.</small></div> : null}

          {selectedDefinition.category === "output" ? <>
            <div className="visual-flow-locked-field"><span>Result</span><strong>{selectedDefinition.type === "output.notify_me" ? "Send me a LifeOS notification" : selectedDefinition.type === "output.save_review_result" ? "Keep the result in run history" : "Show me a suggested next action"}</strong><small>This step does not directly change your workspace.</small></div>
            <div className="visual-flow-locked-field"><span>Safety</span><strong>No automatic workspace changes</strong><small>If a change is suggested, you still decide whether it happens.</small></div>
          </> : null}

          {selectedDefinition.category === "proposal" ? <div className="visual-flow-locked-field"><span>Needs your approval</span><strong>LifeOS will ask before changing anything</strong><small>This step prepares a suggestion only. You confirm or reject it.</small></div> : null}

          

          <details className="visual-flow-advanced-node"><summary>Advanced details</summary><div className="visual-flow-node-meta"><span>Step ID</span><code>{selectedNode.id}</code></div>{selectedDefinition.compiler ? <div className="visual-flow-node-meta"><span>Approved capability</span><code>{selectedDefinition.compiler.capability}</code></div> : null}</details>
          <button type="button" className="secondary-button danger-soft" onClick={() => removeNode(selectedNode.id)}>Remove step</button>
        </>}

        <div className={`visual-flow-validation ${validationIssues.length ? "has-errors" : "valid"}`}>
          <div><strong>{validationIssues.length ? "Almost ready" : "Ready to save"}</strong><span>{validationIssues.length ? `${validationIssues.length} thing${validationIssues.length === 1 ? "" : "s"} to fix` : "LifeOS understands the flow"}</span></div>
          {validationIssues.length ? <ul>{validationIssues.map((issue) => <li key={issue}>{issue}</li>)}</ul> : <p>LifeOS will validate the same flow again on the backend before it can run.</p>}
        </div>
      </aside>
    </div>

    <div className="visual-flow-contract">
      <span>✓ Approved LifeOS steps only</span><span>✓ No direct database writes</span><span>✓ Important changes ask first</span><span>✓ Run history keeps evidence</span>
    </div>
  </section>;
}
