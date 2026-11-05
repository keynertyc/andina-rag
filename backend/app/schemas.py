from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ReviewAction = Literal["edit", "approve", "reject", "reopen", "regenerate"]


class Product(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=5000)
    brand: str = Field(min_length=1, max_length=100)
    category: str = Field(min_length=1, max_length=100)
    tags: list[str] = Field(default_factory=list, max_length=20)


class GeneratedProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=4000)
    tags: list[str] = Field(min_length=1, max_length=10)
    citations: list[str] = Field(min_length=1, max_length=10)

    @field_validator("tags", "citations")
    @classmethod
    def unique_nonempty_values(cls, values: list[str]) -> list[str]:
        if any(not value.strip() or len(value) > 100 for value in values):
            raise ValueError("Los valores deben tener entre 1 y 100 caracteres")
        if len(values) != len(set(values)):
            raise ValueError("Los valores deben ser únicos")
        return values


class ProposalUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, min_length=1, max_length=4000)
    tags: list[str] | None = Field(default=None, min_length=1, max_length=10)
    status: Literal["pending_review", "approved", "rejected"] | None = None


class DocumentUploadResult(BaseModel):
    document_id: str
    version_id: str
    status: str


class DocumentView(BaseModel):
    id: str
    title: str
    brand: str | None
    category: str | None
    version_id: str
    version: int
    status: str
    is_active: bool
    error: dict[str, Any] | None
    filename: str


class BatchView(BaseModel):
    id: str
    filename: str
    created_at: datetime
    status: Literal["pending", "running", "completed", "with_errors"]
    total: int
    finished: int
    terminal: bool
    counts: dict[str, int]
    dispatch_error: dict[str, Any] | None
    configuration: dict[str, Any]


class BatchItemView(BaseModel):
    id: str
    product_id: str
    original: Product
    status: str
    attempts: int
    error: dict[str, Any] | None


class CitationView(BaseModel):
    id: str
    text: str
    document_title: str
    version: int
    page: int | None
    heading: str | None


class ProposalView(BaseModel):
    id: str
    item_id: str
    batch_id: str
    product_id: str
    original: Product
    content: GeneratedProposal
    status: Literal["pending_review", "approved", "rejected"]
    revision: int
    is_stale: bool
    allowed_actions: list[ReviewAction]
    created_at: datetime


class ProposalDetailView(ProposalView):
    generated: GeneratedProposal
    citations: list[CitationView]
