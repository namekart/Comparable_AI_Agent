"""
Restore Supabase embeddings from a backup file
"""
import psycopg2
from psycopg2.extras import Json
import json
import os
from dotenv import load_dotenv

load_dotenv()

# Ask user which backup to restore
backup_dir = "backups"
backups = sorted([f for f in os.listdir(backup_dir) if f.endswith('.json')])

if not backups:
    print("❌ No backup files found in backups/")
    exit(1)

print("Available backups:")
for i, backup in enumerate(backups, 1):
    size = os.path.getsize(f"{backup_dir}/{backup}") / (1024*1024)
    print(f"  {i}. {backup} ({size:.2f} MB)")

choice = int(input("\nSelect backup to restore (number): "))
backup_file = f"{backup_dir}/{backups[choice-1]}"

print(f"\n🔹 Loading backup: {backup_file}")
with open(backup_file, 'r') as f:
    backup_data = json.load(f)

print(f"✅ Loaded {len(backup_data)} embeddings")

print("🔹 Connecting to Supabase...")
conn = psycopg2.connect(
    host=os.getenv("SUPABASE_HOST"),
    port=os.getenv("SUPABASE_PORT", "5432"),
    dbname=os.getenv("SUPABASE_DB", "postgres"),
    user=os.getenv("SUPABASE_USER", "postgres"),
    password=os.getenv("SUPABASE_PASSWORD")
)
cursor = conn.cursor()

print("🔹 Clearing current data...")
cursor.execute("DELETE FROM domain_embeddings")
conn.commit()

print("🔹 Restoring embeddings...")
for i, item in enumerate(backup_data, 1):
    cursor.execute(
        """
        INSERT INTO domain_embeddings (content, metadata, embedding)
        VALUES (%s, %s, %s)
        """,
        (
            item['content'],
            Json(item['metadata']),
            f'[{",".join(map(str, item["embedding"]))}]'
        )
    )
    
    if i % 100 == 0:
        conn.commit()
        print(f"   Restored {i}/{len(backup_data)} embeddings...")

conn.commit()
print(f"✅ Restored {len(backup_data)} embeddings")

cursor.close()
conn.close()

print("🎉 Restore complete!")