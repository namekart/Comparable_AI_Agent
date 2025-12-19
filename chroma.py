#!/usr/bin/env python3
"""
Script to check what's actually stored in ChromaDB.
Provides detailed statistics and sample data.
"""

import chromadb
from chromadb.config import Settings
import config
from collections import Counter

def check_chroma():
    """Check ChromaDB contents with detailed statistics"""

    print("\n" + "="*80)
    print("CHROMADB DATABASE INSPECTION")
    print("="*80)

    # Initialize ChromaDB client
    client = chromadb.PersistentClient(
        path=config.CHROMA_PERSIST_DIR,
        settings=Settings(anonymized_telemetry=False)
    )

    # Get collection
    try:
        collection = client.get_or_create_collection(
            name=config.CHROMA_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"}
        )
    except Exception as e:
        print(f"Error accessing collection: {e}")
        return

    # Get all documents
    try:
        results = collection.get(include=["documents", "metadatas"])
    except Exception as e:
        print(f"Error retrieving data: {e}")
        return

    total_docs = len(results['documents'])
    
    if total_docs == 0:
        print("\n❌ ChromaDB is EMPTY! No documents found.")
        print("\nYou need to run: python build_and_export_embeddings.py")
        return

    print(f"\n📊 TOTAL DOCUMENTS: {total_docs}")
    print(f"📁 Database Location: {config.CHROMA_PERSIST_DIR}")
    print(f"📦 Collection Name: {config.CHROMA_COLLECTION_NAME}")

    # Extract metadata for analysis
    metadatas = results['metadatas']
    
    # Count unique domains (since we have 2 descriptions per domain)
    unique_domains = set(m.get('domain', '') for m in metadatas)
    print(f"🌐 UNIQUE DOMAINS: {len(unique_domains)}")

    # TLD breakdown
    print(f"\n{'='*80}")
    print("TLD DISTRIBUTION")
    print("="*80)
    tld_counts = Counter(m.get('tld', 'unknown') for m in metadatas)
    for tld, count in tld_counts.most_common(15):
        print(f"  {tld:<15} {count:>6} documents")

    # Category breakdown
    print(f"\n{'='*80}")
    print("PRIMARY CATEGORY DISTRIBUTION")
    print("="*80)
    cat_counts = Counter(m.get('primary_category', 'unknown') for m in metadatas)
    for cat, count in cat_counts.most_common(10):
        print(f"  {cat:<25} {count:>6} documents")

    # Price statistics
    print(f"\n{'='*80}")
    print("PRICE STATISTICS")
    print("="*80)
    prices = [m.get('price', 0) for m in metadatas if m.get('price', 0) > 0]
    if prices:
        print(f"  Min Price:     ${min(prices):>12,.0f}")
        print(f"  Max Price:     ${max(prices):>12,.0f}")
        print(f"  Avg Price:     ${sum(prices)/len(prices):>12,.0f}")
        print(f"  Total Value:   ${sum(prices):>12,.0f}")

    # Date range
    print(f"\n{'='*80}")
    print("DATE RANGE")
    print("="*80)
    dates = [m.get('date', '') for m in metadatas if m.get('date', '')]
    if dates:
        dates_sorted = sorted(dates)
        print(f"  Earliest Sale: {dates_sorted[0]}")
        print(f"  Latest Sale:   {dates_sorted[-1]}")

    # Length distribution
    print(f"\n{'='*80}")
    print("DOMAIN LENGTH DISTRIBUTION")
    print("="*80)
    lengths = [m.get('length', 0) for m in metadatas]
    length_ranges = {
        "1-3 chars": len([l for l in lengths if 1 <= l <= 3]),
        "4-6 chars": len([l for l in lengths if 4 <= l <= 6]),
        "7-10 chars": len([l for l in lengths if 7 <= l <= 10]),
        "11-15 chars": len([l for l in lengths if 11 <= l <= 15]),
        "16+ chars": len([l for l in lengths if l > 15])
    }
    for range_name, count in length_ranges.items():
        print(f"  {range_name:<15} {count:>6} documents")

    # Sample domains
    print(f"\n{'='*80}")
    print("SAMPLE DOMAINS (First 10)")
    print("="*80)
    
    shown = set()
    count = 0
    for doc, metadata in zip(results['documents'][:30], results['metadatas'][:30]):
        domain = metadata.get('domain', 'unknown')
        if domain in shown:
            continue
        shown.add(domain)
        count += 1
        
        print(f"\n{count}. Domain: {domain}")
        print(f"   TLD: {metadata.get('tld', 'N/A')}, Length: {metadata.get('length', 'N/A')}")
        print(f"   Categories: {metadata.get('primary_category', 'N/A')} / {metadata.get('secondary_category', 'N/A')}")
        print(f"   Price: ${metadata.get('price', 0):,.0f}, Date: {metadata.get('date', 'N/A')}")
        print(f"   Platform: {metadata.get('platform', 'N/A')}")
        print(f"   Description: {doc[:100]}...")
        
        if count >= 10:
            break

    # Check for numeric domains
    print(f"\n{'='*80}")
    print("NUMERIC DOMAINS CHECK")
    print("="*80)
    has_numbers_count = sum(1 for m in metadatas if m.get('has_numbers', False))
    print(f"  Domains with numbers: {has_numbers_count}")
    print(f"  Domains without:      {total_docs - has_numbers_count}")

    print(f"\n{'='*80}")
    print("✅ DATABASE CHECK COMPLETE")
    print("="*80)
    
    if total_docs < 100:
        print("\n⚠️  WARNING: You only have a small test dataset!")
        print("   To load your real data, run: python build_and_export_embeddings.py")

if __name__ == "__main__":
    check_chroma()