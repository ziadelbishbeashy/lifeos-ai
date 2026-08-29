# I18 — Visual Flow Studio

I18 adds a visual authoring layer on top of the activated I17 intelligence automation engine. It does **not** create a second workflow runtime.

## V1 flow contract

Every visual flow contains three reviewed nodes:

1. **Trigger** — daily, weekly, or an allow-listed I14 event.
2. **LifeOS Intelligence** — one allow-listed I17 intelligence action.
3. **Notify** — in-app delivery through I14/I15.

The nodes are draggable and their positions are persisted in `lifeos_automations.visual_graph_json`. The execution semantics remain in the existing `trigger_type`, `trigger_config_json`, `action_type`, and `action_config_json` columns.

## Safety

- Visual JSON is layout metadata, not executable code.
- The backend rejects extra nodes, rewired edges, arbitrary URLs, arbitrary code, and unsupported node kinds.
- Project-scoped actions are revalidated against the authenticated owner when a flow is saved.
- The canvas cannot enable workspace mutation. Future mutation nodes must remain behind I9 confirmation.
- I17 remains the only automation executor; I18 is an authoring/view layer.

## UI

`Automations` now provides **Visual Flow** in addition to the existing quick builder. Existing I17 automations can be opened in the visual studio and automatically receive a safe default layout if they predate I18.

## Migration

I18 adds one additive column only:

- `lifeos_automations.visual_graph_json`

Migration head: `20260830_0002`.
