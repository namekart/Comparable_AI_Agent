from datetime import datetime
from typing import List, Dict
import config

def get_tld_family(tld: str) -> str:
    """Return the TLD family for a given TLD"""
    for family, tlds in config.TLD_FAMILIES.items():
        if tld in tlds:
            return family
    return "other"

def build_where_clause(
    tld: str,
    length: int,
    primary_category: str,
    secondary_category: str,
    include_tld_filter: bool = True
) -> Dict:
    """Build ChromaDB where clause for hard filters.

    Filters:
    1. TLD family match (optional)
    2. Length within ±2
    3. Category overlap (at least one category matches)
    
    Args:
        tld: Input domain TLD
        length: Input domain length
        primary_category: Input domain primary category
        secondary_category: Input domain secondary category
        include_tld_filter: Whether to include TLD filter (default: True)
    """
    tld_family = get_tld_family(tld)

    # TLD filter logic
    if tld_family == "other":
        # Unknown TLD - try exact match
        tld_filter = tld
    else:
        # Known family - use the entire family list
        tld_filter = config.TLD_FAMILIES[tld_family]

    # Build base filters (length + category)
    where = {
        "$and": [
            {"length": {"$gte": length - config.MAX_LENGTH_DIFF}},
            {"length": {"$lte": length + config.MAX_LENGTH_DIFF}},
            
            # Category filter (always applied)
            {
                "$or": [
                    {"primary_category": {"$in": [primary_category, secondary_category]}},
                    {"secondary_category": {"$in": [primary_category, secondary_category]}},
                ]
            }
        ]
    }
    
    # Add TLD filter only if include_tld_filter is True
    if include_tld_filter:
        where["$and"].insert(2, {"tld": {"$in": tld_filter if isinstance(tld_filter, list) else [tld_filter]}})
    
    return where

def apply_length_band_filter(candidates: List[Dict], target_length: int) -> List[Dict]:
    """
    Post-filter to ensure length band (in case Chroma didn't filter perfectly).
    """
    return [
        c for c in candidates
        if abs(c["metadata"]["length"] - target_length) <= config.MAX_LENGTH_DIFF
    ]




