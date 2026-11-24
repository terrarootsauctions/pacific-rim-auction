"""
Workflow graph engine (PURE, standard library only).

A small node-and-edge runner for the platform's multi-step pipeline. Node
kinds: agent, tool, condition (picks a branch), approval (pauses until a
human approves). Every run has a step limit and returns a full trace, so
the architect can see exactly what ran and where it stopped.

The engine takes handlers as plain functions, so the pipeline can be tested
without any service. Wiring real handlers to the platform's existing
services (claims, listing gate, auction engine, payments) is done where the
run is started; nothing here talks to a database or a bank.

An approval node always stops the run until its id is in `approvals`. There
is no setting that skips an approval.
"""
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set, Tuple

KINDS = frozenset({"agent", "tool", "condition", "approval", "end"})


@dataclass(frozen=True)
class Node:
    id: str
    kind: str
    label: str = ""
    handler: Optional[str] = None  # key into the handlers dict


@dataclass
class Graph:
    nodes: Dict[str, Node] = field(default_factory=dict)
    edges: List[Tuple[str, str, Optional[str]]] = field(default_factory=list)  # (src, dst, branch)

    def add(self, node: Node) -> "Graph":
        if node.kind not in KINDS:
            raise ValueError(f"Unknown node kind: {node.kind}")
        if node.id in self.nodes:
            raise ValueError(f"Duplicate node id: {node.id}")
        self.nodes[node.id] = node
        return self

    def link(self, src: str, dst: str, branch: Optional[str] = None) -> "Graph":
        self.edges.append((src, dst, branch))
        return self

    def out_edges(self, node_id: str):
        return [(d, b) for s, d, b in self.edges if s == node_id]


def validate(graph: Graph, start: str, handlers: Optional[Dict[str, Callable]] = None) -> List[str]:
    """Return a list of problems (empty means the graph is sound)."""
    problems = []
    if start not in graph.nodes:
        return [f"Start node {start!r} does not exist."]
    for s, d, _ in graph.edges:
        for n in (s, d):
            if n not in graph.nodes:
                problems.append(f"Edge references unknown node {n!r}.")
    seen, stack = set(), [start]
    while stack:
        n = stack.pop()
        if n in seen or n not in graph.nodes:
            continue
        seen.add(n)
        stack.extend(d for d, _ in graph.out_edges(n))
    for nid in graph.nodes:
        if nid not in seen:
            problems.append(f"Node {nid!r} is unreachable from the start.")
    for nid, node in graph.nodes.items():
        outs = graph.out_edges(nid)
        if node.kind == "end" and outs:
            problems.append(f"End node {nid!r} has outgoing edges.")
        if node.kind != "end" and not outs:
            problems.append(f"Node {nid!r} is a dead end (not an end node).")
        if node.kind == "condition":
            if any(b is None for _, b in outs):
                problems.append(f"Condition {nid!r} has an unlabeled branch.")
        elif len(outs) > 1:
            problems.append(f"Node {nid!r} has several exits but is not a condition.")
        if node.kind in ("agent", "tool", "condition") and handlers is not None and node.handler not in handlers:
            problems.append(f"Node {nid!r} has no handler {node.handler!r}.")
    return problems


@dataclass
class RunResult:
    status: str  # completed | paused | failed | step_limit
    context: dict
    trace: List[dict]
    waiting_on: Optional[str] = None
    error: Optional[str] = None


def run(graph: Graph, start: str, handlers: Dict[str, Callable], context: Optional[dict] = None,
        approvals: Optional[Set[str]] = None, max_steps: int = 50,
        entry: Optional[str] = None) -> RunResult:
    """Run from `start`. When resuming a paused run, pass the pipeline's
    original `entry` so the graph is still checked as a whole."""
    problems = validate(graph, entry or start, handlers)
    if not problems and start not in graph.nodes:
        problems = [f"Start node {start!r} does not exist."]
    if problems:
        return RunResult("failed", dict(context or {}), [], error="; ".join(problems))
    ctx = dict(context or {})
    approvals = approvals or set()
    trace: List[dict] = []
    current = start
    for step in range(max_steps):
        node = graph.nodes[current]
        if node.kind == "end":
            trace.append({"step": step, "node": current, "event": "end"})
            return RunResult("completed", ctx, trace)
        if node.kind == "approval":
            if current not in approvals:
                trace.append({"step": step, "node": current, "event": "waiting_for_approval"})
                return RunResult("paused", ctx, trace, waiting_on=current)
            trace.append({"step": step, "node": current, "event": "approved"})
            current = graph.out_edges(current)[0][0]
            continue
        try:
            result = handlers[node.handler](ctx)
        except Exception as exc:  # a failed step stops the run; nothing is hidden
            trace.append({"step": step, "node": current, "event": "error", "error": str(exc)})
            return RunResult("failed", ctx, trace, error=f"{current}: {exc}")
        if node.kind == "condition":
            branch = str(result)
            nxt = [d for d, b in graph.out_edges(current) if b == branch]
            if not nxt:
                trace.append({"step": step, "node": current, "event": "no_branch", "branch": branch})
                return RunResult("failed", ctx, trace, error=f"{current}: no edge for branch {branch!r}")
            trace.append({"step": step, "node": current, "event": "branch", "branch": branch})
            current = nxt[0]
        else:
            if isinstance(result, dict):
                ctx.update(result)
            trace.append({"step": step, "node": current, "event": "ran"})
            current = graph.out_edges(current)[0][0]
    return RunResult("step_limit", ctx, trace, error=f"Stopped after {max_steps} steps.")


# --------------------------------------------------------------------------
# The platform pipeline
# --------------------------------------------------------------------------

def platform_pipeline() -> Graph:
    """Registry scan -> compliance gate -> route (physical property goes via
    TerraRoots) -> valuation and listing -> human approval -> marketplace
    closing -> fee record. Blocked assets stop at the gate."""
    g = Graph()
    g.add(Node("registry_scan", "agent", "Scan and verify the registry record", "registry_scan"))
    g.add(Node("compliance_gate", "condition", "Do No Harm and jurisdiction gate", "compliance_gate"))
    g.add(Node("route_property", "condition", "Physical property or other asset", "route_property"))
    g.add(Node("terraroots_handoff", "agent", "Hand physical property to TerraRoots", "terraroots_handoff"))
    g.add(Node("valuation_listing", "agent", "Value the asset and prepare the listing", "valuation_listing"))
    g.add(Node("listing_approval", "approval", "Architect approves the listing"))
    g.add(Node("marketplace_close", "agent", "Run the auction through closing", "marketplace_close"))
    g.add(Node("record_expected_fee", "tool", "Record the expected fee (receive-only)", "record_expected_fee"))
    g.add(Node("done", "end", "Complete"))
    g.add(Node("blocked", "end", "Blocked by the compliance gate"))
    g.link("registry_scan", "compliance_gate")
    g.link("compliance_gate", "route_property", "cleared")
    g.link("compliance_gate", "blocked", "blocked")
    g.link("route_property", "terraroots_handoff", "physical")
    g.link("route_property", "valuation_listing", "other")
    g.link("terraroots_handoff", "valuation_listing")
    g.link("valuation_listing", "listing_approval")
    g.link("listing_approval", "marketplace_close")
    g.link("marketplace_close", "record_expected_fee")
    g.link("record_expected_fee", "done")
    return g


def describe(graph: Graph) -> dict:
    return {
        "nodes": [{"id": n.id, "kind": n.kind, "label": n.label} for n in graph.nodes.values()],
        "edges": [{"from": s, "to": d, "branch": b} for s, d, b in graph.edges],
    }
