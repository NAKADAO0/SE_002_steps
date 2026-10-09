"""Serializable contracts shared by all workflow nodes."""
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4
from pydantic import BaseModel, Field, field_validator


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentMessage(BaseModel):
    sender: str
    receiver: str
    payload: dict[str, Any]
    revision: int
    timestamp: str = Field(default_factory=now)


class WorkflowEvent(BaseModel):
    kind: str
    node: str
    message: str = ""
    timestamp: str = Field(default_factory=now)


class WorkflowState(BaseModel):
    run_id: str = Field(default_factory=lambda: uuid4().hex)
    requirement: str
    source_code: str = ""
    source_filename: str = ""
    intent: Literal["generate", "review_fix", "review_only"] = "generate"
    mode: Literal["demo", "live"] = "live"
    code: str = ""
    revisions: list[str] = Field(default_factory=list)
    issues: list[dict[str, Any]] = Field(default_factory=list)
    summary: str = ""
    messages: list[AgentMessage] = Field(default_factory=list)
    events: list[WorkflowEvent] = Field(default_factory=list)
    status: Literal["pending", "running", "completed", "failed", "needs_attention"] = "pending"
    next_node: str = "code"
    repairs: int = 0
    max_repairs: int = Field(default=2, ge=0, le=10)
    steps: int = 0
    max_steps: int = Field(default=12, ge=1, le=100)
    error: str = ""

    @field_validator("requirement")
    @classmethod
    def nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("需求不能为空")
        return value.strip()
