import chromadb

from sentence_transformers import SentenceTransformer
from Config.setting import VECTOR_DB_PATH, EMBEDDING_MODEL


class VectorDB:

    def __init__(self):
        
        self.client = chromadb.PersistentClient(
            path=VECTOR_DB_PATH
        )

        
        self.embedding_model = SentenceTransformer(EMBEDDING_MODEL)

        self.law_collection = self.client.get_or_create_collection(
            name="law_collection"
        )

        self.knowledge_collection = self.client.get_or_create_collection(
            name="knowledge_collection"
        )

    def embed(self, texts):
        return self.embedding_model.encode(texts).tolist()

    def add_documents(self, texts, metadatas, ids, collection):

        embeddings = self.embed(texts)

        collection.add(
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids
        )

    def query(self, query_text, collection, n_results=5):

        embedding = self.embed([query_text])[0]

        results = collection.query(
            query_embeddings=[embedding],
            n_results=n_results
        )

        return results

    def list_sources(self, collection):
        """List unique source values in a collection."""
        count = collection.count()
        if count == 0:
            return []
        batch = collection.get(limit=count, include=["metadatas"])
        sources = set()
        for meta in batch.get("metadatas", []):
            src = meta.get("source", "")
            if src:
                sources.add(src)
        return sorted(sources)

    def count_by_source(self, collection, source):
        """Count chunks belonging to a specific source."""
        results = collection.get(
            where={"source": source},
            include=[]
        )
        return len(results.get("ids", []))

    def delete_by_source(self, collection, source):
        """Delete all chunks belonging to a specific source."""
        results = collection.get(
            where={"source": source},
            include=[]
        )
        ids = results.get("ids", [])
        if ids:
            collection.delete(ids=ids)
        return len(ids)

    def find_duplicate_by_content(self, collection, sample_text, threshold=0.92):
        """Check if similar content already exists using embedding similarity.
        Returns (is_duplicate, matched_source) tuple."""
        if collection.count() == 0:
            return False, ""
        embedding = self.embed([sample_text])[0]
        results = collection.query(
            query_embeddings=[embedding],
            n_results=1,
            include=["metadatas", "distances"]
        )
        distances = results.get("distances", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        if distances:
            similarity = 1 - distances[0]
            if similarity >= threshold:
                source = metadatas[0].get("source", "") if metadatas else ""
                return True, source
        return False, ""