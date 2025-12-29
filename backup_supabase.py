"""
Backup current Supabase embeddings to a file
"""
import psycopg2
from psycopg2.extras import RealDictCursor
import pandas as pd
import json
import os
from dotenv import load_dotenv
from datetime import datetime

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
cursor.execute("""
    SELECT 
        id,
        content,
        metadata,
        embedding
    FROM domain_embeddings
""")
rows = cursor.fetchall()

print(f"✅ Found {len(rows)} embeddings")

# Convert to list of dicts
backup_data = []
for row in rows:
    backup_data.append({
        'id': str(row['id']),
        'content': row['content'],
        'metadata': row['metadata'],
        'embedding': row['embedding']  # This is already a list
    })

# Save to JSON file with timestamp
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup_file = f"backups/supabase_backup_{timestamp}.json"

os.makedirs("backups", exist_ok=True)

with open(backup_file, 'w') as f:
    json.dump(backup_data, f, indent=2)

print(f"✅ Backup saved to: {backup_file}")
print(f"   File size: {os.path.getsize(backup_file) / (1024*1024):.2f} MB")

cursor.close()
conn.close()

print("🎉 Backup complete!")