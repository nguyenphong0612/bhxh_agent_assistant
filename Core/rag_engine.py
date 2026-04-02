import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Vector_store.database import VectorDB


class RAGEngine:

    def __init__(self):
        self.vector_db = VectorDB()
        self.law_collection = self.vector_db.law_collection
        self.knowledge_collection = self.vector_db.knowledge_collection

    # --------------------------------------------------
    # Retrieve from each collection
    # --------------------------------------------------

    def retrieve_laws(self, query, n_results=5):
        return self.vector_db.query(
            query_text=query,
            collection=self.law_collection,
            n_results=n_results,
        )

    def retrieve_knowledge(self, query, n_results=5):
        return self.vector_db.query(
            query_text=query,
            collection=self.knowledge_collection,
            n_results=n_results,
        )

    # --------------------------------------------------
    # Rank & deduplicate results from both collections
    # --------------------------------------------------

    def rank_results(self, law_results, knowledge_results, top_k=6):
        """Merge, score, deduplicate and return top_k (doc, meta, origin) tuples."""
        ranked = []

        def _extract(results, origin, boost=0.0):
            docs = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            dists = results.get("distances", [[]])[0]
            for doc, meta, dist in zip(docs, metas, dists):
                # L2 distance → score in [0, 1]: closer = higher
                score = 1.0 / (1.0 + dist) + boost
                # Bonus if chunk contains a specific Điều (article)
                if meta.get("article"):
                    score += 0.05
                ranked.append((score, doc, meta, origin))

        _extract(law_results, "law", boost=0.05)
        _extract(knowledge_results, "knowledge", boost=0.0)

        ranked.sort(key=lambda x: x[0], reverse=True)

        seen = set()
        final = []
        for score, doc, meta, origin in ranked:
            text_key = doc.strip()[:200]  # dedup on first 200 chars
            if text_key not in seen:
                seen.add(text_key)
                final.append((doc, meta, origin))
            if len(final) >= top_k:
                break
        return final

    # --------------------------------------------------
    # Format ranked results into readable context string
    # --------------------------------------------------

    def format_context(self, ranked_docs):
        """Build a labelled context string from ranked (doc, meta, origin) tuples."""
        blocks = []
        for doc, meta, origin in ranked_docs:
            source = meta.get("source", "")
            article = meta.get("article", "")
            issuer = meta.get("issuer", "")

            # Build tag
            if origin == "law":
                tag = "[LUẬT"
                if article:
                    tag += f" - {article}"
                tag += "]"
            else:
                tag = "[TÀI LIỆU"
                if issuer:
                    tag += f" - {issuer}"
                tag += "]"

            # Source line (short — just first 80 chars)
            source_line = f"Nguồn: {source[:80]}" if source else ""

            block = f"{tag}\n{doc.strip()}"
            if source_line:
                block += f"\n({source_line})"
            blocks.append(block)

        return "\n\n".join(blocks)

    # --------------------------------------------------
    # Main entry point: retrieve → rank → format
    # --------------------------------------------------

    def retrieve_context(self, query, n_results=5):
        """Full pipeline: query both collections, rank, format."""
        law_results = self.retrieve_laws(query, n_results)
        knowledge_results = self.retrieve_knowledge(query, n_results)

        ranked = self.rank_results(law_results, knowledge_results)

        if not ranked:
            return ""

        return self.format_context(ranked)
    