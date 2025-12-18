from typing import TypedDict, List, Dict, Optional
from pydantic import BaseModel

class AgentState(TypedDict):
    """ State for the domain comparable agent"""
    # Input
    input_domain: str

    # Parsed features 
    sld: str
    tld: str
    length: int

    # LLM enrichment
    primary_category: str
    secondary_category: str
    descriptions: List[str]

    # Query building
    queries: List[str]

    # Retrieval
    raw_candidates: List[Dict]

    # Scoring
    scored_comparables: List[Dict]

    # Output
    result: Optional[Dict]

    # Error Handling
    error: Optional[str]


class ComparableResult(BaseModel):
    """ Schema for a single comparable domain"""

    domain: str
    price: float
    date: str
    platform: str
    primary_category: str
    secondary_category: str
    semantic_sim: float
    score: float
    description: Optional[str] = None
