"""
Run this file ONCE to:
1. Read CSV
2. Create embeddings
3. Store them in ChromaDB (local)
4. Export embeddings to a portable file

SAFE for Windows + Python 3.11
"""

import os
import time
import pandas as pd
import chromadb
from sentence_transformers import SentenceTransformer
import tldextract

# =========================
# CONFIG — EDIT ONLY THIS
# =========================

# 🔹 Path to your CSV file
CSV_FILE = "data/combined.csv"

# 🔹 Where ChromaDB will be created (DO NOT MOVE AFTER)
CHROMA_DB_DIR = "chroma_db"

# 🔹 Exported embeddings file (portable & safe)
EXPORT_FILE = "data/domain_embeddings.parquet"

COLLECTION_NAME = "domain_embeddings"
MODEL_NAME = "all-MiniLM-L6-v2"
BATCH_SIZE = 50

# =========================
# 1. LOAD CSV
# =========================
print("🔹 Loading CSV...")

if not os.path.exists(CSV_FILE):
    raise FileNotFoundError(f"CSV file not found: {CSV_FILE}")

df = pd.read_csv(CSV_FILE)
print(f"✅ Loaded {len(df)} rows")

# =========================
# 2. LOAD MODEL
# =========================
print("🔹 Loading embedding model...")
model = SentenceTransformer(MODEL_NAME)

# =========================
# 3. INIT CHROMA (LOCAL)
# =========================
print("🔹 Initializing ChromaDB...")

client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
collection = client.get_or_create_collection(
    COLLECTION_NAME,
    metadata={"hnsw:space": "cosine"}
)

print(f"✅ ChromaDB path: {CHROMA_DB_DIR}")

# =========================
# 4. EMBEDDING LOOP
# =========================
batch_ids, batch_docs, batch_metas = [], [], []
total = 0

print("🔹 Generating embeddings...")

for _, row in df.iterrows():

    domain_raw = row.get("domain")
    if pd.isna(domain_raw):
        continue

    domain = str(domain_raw).strip()
    if not domain:
        continue

    try:
        price = float(
            str(row.get("price", "0"))
            .replace("$", "")
            .replace(",", "")
        )
    except:
        price = 0.0

    extracted = tldextract.extract(domain)
    sld = extracted.domain
    tld = f".{extracted.suffix}" if extracted.suffix else ".com"
    length = len(sld)

    # Get both descriptions
    desc_1 = str(row.get("description_1", "")).strip()
    desc_2 = str(row.get("description_2", "")).strip()

    # Create list of descriptions to embed (skip empty ones)
    descriptions = []
    if desc_1:
        descriptions.append((desc_1, 1))
    if desc_2:
        descriptions.append((desc_2, 2))

    # If no descriptions, skip this domain
    if not descriptions:
        continue

    # Create ONE embedding per description
    for desc_text, desc_idx in descriptions:
        
        # Unique ID for each embedding: domain + desc_index
        embedding_id = f"{domain}__desc{desc_idx}"
        
        # Skip if already embedded
        try:
            if collection.get(ids=[embedding_id])["ids"]:
                continue
        except:
            pass

        # Build text for this specific description
        text = (
            f"Domain: {domain}. "
            f"Category: {row.get('primary_category','Unknown')}, "
            f"{row.get('secondary_category','Unknown')}. "
            f"Description: {desc_text}"
        )

        # Metadata with desc_index
        meta = {
            "domain": domain,
            "tld": tld,
            "length": length,
            "price": price,
            "platform": str(row.get("platform", "")),
            "date": str(row.get("date", "")),
            "primary_category": str(row.get("primary_category", "")),
            "secondary_category": str(row.get("secondary_category", "")),
            "desc_index": desc_idx
        }

        batch_ids.append(embedding_id)
        batch_docs.append(text)
        batch_metas.append(meta)

        # Process batch
        if len(batch_ids) >= BATCH_SIZE:
            embeddings = model.encode(
                batch_docs,
                normalize_embeddings=True
            ).tolist()

            collection.upsert(
                ids=batch_ids,
                documents=batch_docs,
                metadatas=batch_metas,
                embeddings=embeddings
            )

            total += len(batch_ids)
            print(f"✅ Embedded {total} descriptions")

            batch_ids, batch_docs, batch_metas = [], [], []

# FINAL BATCH
if batch_ids:
    embeddings = model.encode(
        batch_docs,
        normalize_embeddings=True
    ).tolist()

    collection.upsert(
        ids=batch_ids,
        documents=batch_docs,
        metadatas=batch_metas,
        embeddings=embeddings
    )
    
    total += len(batch_ids)
    print(f"✅ Final batch embedded. Total: {total} descriptions")

# =========================
# 5. EXPORT EMBEDDINGS (SAFE)
# =========================
print("🔹 Exporting embeddings...")

data = collection.get(
    include=["embeddings", "metadatas", "documents"]
)

# Create DataFrame without embeddings first (to avoid 2D array issue)
export_df = pd.DataFrame({
    "id": data["ids"],
    "document": data["documents"],
    **{
        k: [m.get(k) for m in data["metadatas"]]
        for k in data["metadatas"][0].keys()
    }
})

# Add embeddings as a list column (pandas handles this correctly)
export_df["embedding"] = data["embeddings"]

os.makedirs(os.path.dirname(EXPORT_FILE), exist_ok=True)
export_df.to_parquet(EXPORT_FILE, index=False)

print(f"✅ Embeddings exported to: {EXPORT_FILE}")

# =========================
# 6. CLEAN SHUTDOWN
# =========================
print("🔹 Finalizing...")
del collection
del client
time.sleep(2)

print("🎉 DONE — embeddings created & saved safely")
