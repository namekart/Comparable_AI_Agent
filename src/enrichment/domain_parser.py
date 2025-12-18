import tldextract
import re

def parse_domain(domain_name: str) -> dict:
    """ 
    Extract SLD, TLD, and compute basic features from domain.

    Args:
       domain_name: e.g. , "harmonyfoundationinc.com"

    Returns:
       dict with sld, tld, length, is_multi_word
    """
    # Remove protocol if present
    domain_name = domain_name.replace("http://", "").replace("https://", "")
    domain_name = domain_name.split("/")[0]

    # Extract parts
    extracted = tldextract.extract(domain_name)
    sld = extracted.domain
    tld = f".{extracted.suffix}" if extracted.suffix else ".com"

    # Compute features
    length = len(sld)

    # Check if multi-word (has hyphens or CamelCase)
    has_hyphens = "-" in sld
    has_camel_case = bool(re.search(r'[a-z][A-Z]', sld))
    is_multi_word = has_hyphens or has_camel_case

    return {
        "sld": sld,
        "tld": tld,
        "length": length,
        "is_multi_word": is_multi_word
    }


    