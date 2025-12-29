"""
Update existing Supabase embeddings to add missing metadata fields
(length, tld, has_numbers) WITHOUT deleting embeddings
"""
import psycopg2
from psycopg2.extras import RealDictCursor, Json
import tldextract
import os
from dotenv import load_dotenv

load_dotenv()

print("🔹 Connecting to Supabase...")
conn = psycopg2.connect(
    host=os.getenv("SUPABASE_HOST"),
    port=os.getenv("SUPABASE_PORT", "5432"),
    dbname=os.getenv("SUPABASE_DB", "postgres"),
    user=os.getenv("SUPABASE_USER", "postgres"),
    password=os.getenv("SUPABASE_PASSWORD"),
    cursor_factory=RealDictCursor
)
cursor = conn.cursor()

print("🔹 Fetching all embeddings...")
cursor.execute("SELECT id, metadata FROM domain_embeddings")
rows = cursor.fetchall()

print(f"✅ Found {len(rows)} embeddings to update")

updated = 0
for row in rows:
    metadata = row['metadata']
    
    # Check if fields are missing
    if 'length' not in metadata or metadata['length'] is None:
        domain = metadata.get('domain', '')
        
        # Calculate missing fields
        extracted = tldextract.extract(domain)
        sld = extracted.domain
        tld = '.' + extracted.suffix if extracted.suffix else ''
        
        # Add missing fields to metadata
        metadata['length'] = len(sld)
        metadata['tld'] = tld
        metadata['has_numbers'] = any(c.isdigit() for c in sld)
        
        # Update the row
        cursor.execute(
            "UPDATE domain_embeddings SET metadata = %s WHERE id = %s",
            (Json(metadata), row['id'])
        )
        
        updated += 1
        
        if updated % 100 == 0:
            conn.commit()
            print(f"   Updated {updated} rows...")

conn.commit()
print(f"✅ Updated {updated} embeddings with calculated metadata")

cursor.close()
conn.close()

print("🎉 Update complete! Embeddings preserved, metadata enriched.")