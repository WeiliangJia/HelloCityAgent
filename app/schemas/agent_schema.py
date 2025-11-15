from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class AgentDecision(BaseModel):
    """Structured response from the judge agent describing what to do next."""

    action: Literal["chat", "rag", "search_flight", "search_hotel", "search_general"] = Field(
        ...,
        description="Routing decision for the workflow.",
    )
    reason: str = Field(..., description="Short explanation for the chosen action.")
    search_query: Optional[str] = Field(
        default=None,
        description="Concrete web search query to execute when action is search_*.",
    )
    confidence: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Confidence score for the selected action.",
    )
    followups: List[str] = Field(
        default_factory=list,
        description="Any follow up questions the assistant should ask if more information is needed.",
    )


class PriceQuote(BaseModel):
    """Individual flight or hotel offer extracted from search results."""

    item: str = Field(..., description="Name of the airline route or hotel property.")
    price: Optional[str] = Field(default=None, description="Quoted price with unit if available.")
    currency: Optional[str] = Field(default=None, description="Currency code such as USD, EUR, CNY.")
    url: Optional[str] = Field(default=None, description="Source URL for the offer.")
    notes: Optional[str] = Field(default=None, description="Important conditions or inclusions.")


class SearchSummary(BaseModel):
    """Structured summary of price information returned to the user."""

    reply: str = Field(
        ...,
        description="Final assistant message to send to the user with actionable next steps.",
    )
    key_points: List[str] = Field(
        default_factory=list,
        description="Important bullet points extracted from the search.",
    )
    price_quotes: List[PriceQuote] = Field(
        default_factory=list,
        description="List of the top price quotes discovered.",
    )
    price_range: Optional[str] = Field(
        default=None,
        description="Overall price range (low-high) if derivable.",
    )
    recommendation: Optional[str] = Field(
        default=None,
        description="Suggested best option or advice for the user.",
    )
    caution: Optional[str] = Field(
        default=None,
        description="Disclaimers or cautions about the pricing data.",
    )
