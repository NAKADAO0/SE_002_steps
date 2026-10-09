"""Sequential orchestration; commit outputs only after node validation."""
from .state import AgentMessage, WorkflowEvent, WorkflowState
from .storage import RunStore


class ReviewWorkflow:
    def __init__(self, agents, store: RunStore, routes=None):
        self.agents = agents
        self.store = store
        self.routes = routes or {"code": "review", "fix": "review"}

    def run(self, state: WorkflowState, on_event=None) -> WorkflowState:
        state = state.model_copy(deep=True)
        if state.status in ("completed", "needs_attention"):
            return state
        state.status, state.error = "running", ""

        def event(kind, node, message=""):
            state.events.append(WorkflowEvent(kind=kind, node=node, message=message))
            self.store.save(state)
            if on_event:
                try:
                    on_event(state.model_copy(deep=True))
                except Exception:
                    # A disconnected observer must not alter committed workflow state.
                    pass

        while state.status == "running":
            node = state.next_node
            if state.steps >= state.max_steps:
                state.status = "needs_attention"
                event("step_limit", node, "已达到流程节点次数上限")
                break
            payload = {"requirement": state.requirement, "source_code": state.source_code,
                       "code": state.code, "issues": state.issues, "revision": len(state.revisions),
                       "source_filename": state.source_filename, "intent": state.intent}
            sender = "user" if not state.messages else state.messages[-1].receiver
            state.messages.append(AgentMessage(sender=sender, receiver=node,
                                               payload=payload, revision=len(state.revisions)))
            event("node_started", node)
            try:
                output = self.agents[node].execute(payload, on_step=lambda kind, data:
                    event("agent_" + kind, node, str(data.get("tool", ""))))
                if node == "review":
                    state.issues, state.summary = output["issues"], output["summary"]
                    if not state.issues:
                        state.status = "completed"
                    elif state.repairs >= state.max_repairs:
                        state.status = "needs_attention"
                    else:
                        state.next_node = "fix"
                else:
                    next_node = self.routes[node]
                    state.code = output["code"]
                    state.revisions.append(state.code)
                    if node == "fix":
                        state.repairs += 1
                    state.next_node = next_node
                state.steps += 1
            except Exception as exc:
                state.status, state.error = "failed", str(exc)
                state.next_node = node
                event("node_failed", node, state.error)
            else:
                # Persistence failures propagate without reverting a completed node.
                event("node_completed", node)
        return state
