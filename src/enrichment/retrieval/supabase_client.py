import psycopg2
from psycopg2.extras import RealDictCursor
from sentence_transformers import SentenceTransformer
from typing import List, Dict
import config
import json
import tldextract

class SupabaseClient:
    """ Wrapper for Supabase/ PostgreSQL vector operations(pgvector)"""
    def __init__(self):
        # Initialize embedding model 
        self.embeddings = SentenceTransformer(config.EMBEDDING_MODEL)

        # Connect to SupaBase PostgreSQL
        self.conn = psycopg2.connect(
            host=config.SUPABASE_HOST,
            port=config.SUPABASE_PORT,
            database=config.SUPABASE_DB,
            user=config.SUPABASE_USER,
            password=config.SUPABASE_PASSWORD,
            cursor_factory = RealDictCursor
        )
        self.cursor = self.conn.cursor()

        print(f" Connected to SupaBase PostgreSQL")

    def _enrich_metadata(self, metadata: Dict) -> Dict:
        """
        Enrich metadata with missing fields calculated from domain name.
        Adds: length, tld, has_numbers if they don't exist.
        """
        if 'length' not in metadata or metadata['length'] is None:
            domain = metadata.get('domain', '')
            extracted = tldextract.extract(domain)
            sld = extracted.domain
            tld = '.' + extracted.suffix if extracted.suffix else ''
            
            # Calculate missing fields
            metadata['length'] = len(sld)
            metadata['tld'] = tld
            metadata['has_numbers'] = any(c.isdigit() for c in sld)
        
        return metadata

    
    def query(self, query_texts: List[str], where:Dict, n_results: int = 50) -> List[Dict]:
        """ Query SupaBase with filters(mimics ChromaDB interface)
        Args:
            query_texts: List of description strings to embed and search
            where: Filter clause (will be converted to SQL WHERE)
            n_results: Number of results per query

        Returns:
            List of candidates with metadata and distances

        """

        candidates = []

        for query_text in query_texts:
            # Generate embedding for query
            query_embedding = self.embeddings.encode(query_text).tolist()

            # Build SQL WHERE clause from ChromaDB-style filter
            sql_where = self._build_sql_where(where)

            #Execute vector similarity search
            sql = f"""
                SELECT
                    id,
                    content as document,
                    metadata,
                    embedding <-> %s::vector as distance
                FROM domain_embeddings
                WHERE {sql_where}
                ORDER BY embedding <-> %s::vector
                LIMIT %s;
            """
            
            # Convert embedding list to PostgreSQL array string format
            embedding_str = '[' + ','.join(map(str, query_embedding)) + ']'

            self.cursor.execute(sql, (embedding_str, embedding_str, n_results))
            rows = self.cursor.fetchall()

            # Convert to ChromaDB-compatible format
            for row in rows:
                candidates.append({
                    "id": str(row["id"]),
                    "document": row["document"],
                    "distance": float(row["distance"]),
                    "metadata": row["metadata"]
                })

        return candidates
    

    def _build_sql_where(self, where: Dict) -> str:
        """
        Convert ChromaDB where clause to SQL WHERE clause.

        Example ChromaDB filter:
        {
            "$and": [
                {"length": {"$gte": 5}},
                {"length": {"$lte": 9}},
                {"tld": {"$in": [".com", ".net", ".org"]}}
                {"$or":[
                    {"primary_category": {"$in": ["Brandable", "Descriptive"]}},
                    {"secondary_category": {"$in": ["Brandable", "Descriptive"]}}
                ]}
            ]
        }
        
        Converts to SQL:
        (metadata ->> 'length')::int >= 5 AND (metadata ->> 'length') :: int <= 9
        AND metadata->> 'tld' IN ('.com', '.net', '.org')
        AND (metadata->> 'primary_category' IN ('Brandable', 'Descriptive') 
            OR metadata->> 'secondary_category' IN ('Brandable', 'Descriptive'))
        
        """
        if "$and" in where:
            conditions = []
            for condition in where["$and"]:
                conditions.append(self._parse_condition(condition))
            return " AND ".join(conditions)
        else:
            return self._parse_condition(where)

    
    def _parse_condition(self, condition: Dict) -> str:
        """ Parse a single condition or $or clause"""
        if "$or" in condition:
            or_conditions = []
            for sub_condition in condition ["$or"]:
                or_conditions.append(self._parse_condition(sub_condition))
            return f"({ ' OR '.join(or_conditions)})"

        # Single Field Condition
        for field, operator_dict in condition.items():
            if field.startswith("$"):
                continue

            # Handle field condition
            if "$gte" in operator_dict:
                value = operator_dict["$gte"]
                return f"(metadata->>'{field}')::int >= {value}"

            elif "$lte" in operator_dict:
                value = operator_dict["$lte"]
                return f"(metadata->>'{field}')::int <= {value}"

            elif "$in" in operator_dict:
                values = operator_dict["$in"]
                # Quote string values
                quoted_values = ", ".join([f"'{v}'" for v in values])
                return f"metadata->>'{field}' IN ({quoted_values})"

            elif "$eq" in operator_dict:
                value = operator_dict["$eq"]
                return f"metadata->>'{field}' = '{value}'"

        return "TRUE"
    

    def count(self) -> int:
        """ Return total number of documents in collection """
        self.cursor.execute("SELECT COUNT(*) as count FROM domain_embeddings")
        result = self.cursor.fetchone()
        return result["count"] if result else 0

    def close(self):
        """ Close  database connection """
        self.cursor.close()
        self.conn.close()
        print(" Supabase connection closed")
