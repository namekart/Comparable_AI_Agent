from datetime import datetime
from typing import List, Dict
import config

def compute_category_match(
    candidate_primary: str,
    candidate_secondary: str,
    input_primary: str,
    input_secondary: str
) -> float:
    """
    Compute category match score.
    Returns:
    - 1.0 if primary match exactly
    - 0.7 if secondary overlap
    - 0.5 if compatible types
    - 0.0 otherwise
    """
    if candidate_primary == input_primary:
        return 1.0

    if (candidate_secondary == input_primary) or (candidate_primary == input_secondary):
        return 0.7

    compatible_types = [
        {"Brandable", "Generic"},
        {"Descriptive", "Keyword"},
        {"Service-based", "Product-based"},
        {"Niche", "Generic"},
    ]

    for pair in compatible_types:
        if {candidate_primary, input_primary}.issubset(pair):
            return 0.5

    return 0.0

def compute_tld_match(candidate_tld: str, input_tld: str) -> float:
    """
    Compute TLD match score.
    Returns:
    - 1.0 if exact match
    - 0.7 if same family
    - 0.3 if .com vs other
    - 0.0 otherwise
    """
    if candidate_tld == input_tld:
        return 1.0
    
    from src.enrichment.retrieval.filters import get_tld_family

    candidate_family = get_tld_family(candidate_tld)
    input_family = get_tld_family(input_tld)

    if candidate_family == input_family and candidate_family != "other":
        return 0.7
    
    if candidate_tld == ".com" and input_family == ".com":
        return 0.3

    return 0.0


def compute_recency_weight(sale_data: str) -> float:
    """
    Compute recency weight based on sale data.

    Args:
        sale_date: ISO format data string

    Returns:
       float between 0.3 and 1.0
    """
    try:
        sale_dt = datetime.fromisoformat(sale_date.replace('Z', '+00:00'))
        days_old = (datetime.now(sale_dt.tzinfo)-sale_dt).days

        for threshold, weight in config.RECENCY_BANDS:
            if days_old < threshold:
                return weight
        
        return 0.3
    except Exception:
        return 0.5

def score_candidates(candidates: List[Dict], input_primary: str, input_secondary: str, input_tld:str) -> List[Dict]:
    """ Score and rank all candidates using hybrid strategy.

    Composite score:
       0.6 * semantic_sim + 0.2 * cat_match + 0.2 * recency_weight

    Args:
        candidates: Raw candidates from Chroma with metadata and distances
        input_primary: Input domain primary category
        input_secondary: Input domain secondary category
        input_tld: Input domain TLD

    Returns:
        List of scored candidates sorted by score(descending)
    """
    scored = []

    for candidate in candidates:
        metadata = candidate["metadata"]
        document = candidate.get("document", "")

        # Extract description from document field
        # Handle various document formats (with or without spacing issues)
        # Formats: "Domain: X. Category: Y, Z. Description: ABC"
        #          "Domain: X.Category: Y,Z Description:ABC" (no spaces)
        description = ""
        if document:
            # Try multiple patterns to extract description
            desc_patterns = [
                "Description: ",
                "Description:",
                " Description: ",
                " Description:",
                ".Description:",
                ". Description:"
            ]
            
            for pattern in desc_patterns:
                if pattern in document:
                    desc_start = document.find(pattern)
                    if desc_start != -1:
                        # Extract text after the pattern
                        description = document[desc_start + len(pattern):].strip()
                        break
            
            # Fallback: if still empty, try splitting by Category
            if not description and "Category:" in document:
                parts = document.split("Category:")
                if len(parts) > 1:
                    remaining = parts[1]
                    if "Description" in remaining:
                        desc_part = remaining.split("Description", 1)
                        if len(desc_part) > 1:
                            description = desc_part[1].lstrip(": .").strip()

        # Convert distance to similarity(Chroma uses L2 distance)
        # For cosine distance: similarity = 1- distance
        # For L2: similarity = 1 / (1+distance)

        distance = candidate.get("distance", 0)
        semantic_sim = 1 / (1+distance) if distance >= 0 else 0.5

        # Category match
        cat_match = compute_category_match(
            metadata.get("primary_category",""),
            metadata.get("secondary_category",""),
            input_primary,
            input_secondary
        )
        # TLD match(optional, already filtered)
        tld_match = compute_tld_match(metadata.get("tld",""), input_tld)

        # Recency weight
        recency = compute_recency_weight(metadata.get("date", ""))

        score = (
            config.SCORE_WEIGHTS["semantic"] * semantic_sim +
            config.SCORE_WEIGHTS["category"] * cat_match +
            config.SCORE_WEIGHTS["recency"] * recency
        )

        scored.append({
            "domain": metadata.get("domain"),
            "price": metadata.get("price"),
            "date": metadata.get("date"),
            "platform": metadata.get("platform"),
            "primary_category": metadata.get("primary_category"),
            "secondary_category": metadata.get("secondary_category"),
            "description": description,
            "semantic_sim": round(semantic_sim, 4),
            "cat_match": round(cat_match, 2),
            "recency": round(recency, 2),
            "score": round(score, 4),
            "desc_index": metadata.get("desc_index", 1),
            "query_index": candidate.get("query_index", 0)

        })


    # Filter by threshold
    scored = [c for c in scored if c["score"] >= config.MIN_SCORE_THRESHOLD]

    # Deduplicate by domain, keep highest score per domain
    domain_best = {}
    for candidate in scored:
        domain = candidate["domain"]
        if domain not in domain_best or candidate["score"] > domain_best[domain]["score"]:
            domain_best[domain] = candidate
    
    # Sort by score descending
    final = sorted(domain_best.values(), key=lambda x:x["score"], reverse=True)

    # Keep Top K
    return final[:config.FINAL_TOP_K]

