import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Document_processing.splitter import TextSplitter
from Core.llm_agent import LLMAgent
from Core.rag_engine import RAGEngine
from Vector_store.database import VectorDB
from Core.prompt_manager import PromptManager
import json
import re
import uuid
from Document_processing.metadata_extractor import MetadataExtractor

class LegalAgentWorkflow:

    def __init__(self, model):

        self.splitter = TextSplitter()
        self.llm_agent = LLMAgent(model)
        self.rag_engine = RAGEngine()
        self.vector_db = VectorDB()

        # Use collections from vector_db instance
        self.law_collection = self.vector_db.law_collection
        self.knowledge_collection = self.vector_db.knowledge_collection
    def extract_title(self, text):

        lines = text.strip().split("\n")

        titles = []
        for line in lines[:5]:
            line = line.strip()
            if len(line) > 3 and len(line) < 100:
                titles.append(line)
        title = ""
        for j in range(len(titles)):
            title += " " + titles[j]
        return title

    # --------------------------------------------------
    # 1. INGEST DOCUMENT (add law or knowledge)
    # --------------------------------------------------

    def _build_source_label(self, meta):
        """Build a compact source label from metadata."""
        parts = []
        if meta.get("so_van_ban"):
            parts.append(meta["so_van_ban"])
        if meta.get("tieu_de"):
            parts.append(meta["tieu_de"][:80])
        if parts:
            return " — ".join(parts)
        if meta.get("issuer"):
            return meta["issuer"][:80]
        return "Văn bản không rõ tiêu đề"

    def ingest_preview(self, text):
        """Preview: extract metadata + split chunks without adding to DB."""
        extractor = MetadataExtractor()
        doc_meta = extractor.extract_document(text)
        meta = doc_meta.get("metadata", {})
        body_text = doc_meta.get("body_text", "")

        text_for_split = body_text if body_text else text
        chunks = self.splitter.split_recursive(text_for_split, max_chunk_size=4000)

        source_label = self._build_source_label(meta)

        return {
            "metadata": meta,
            "source_label": source_label,
            "chunks": chunks,
            "chunk_count": len(chunks),
        }

    def ingest_document(self, text, collection_type="law"):
        """Ingest document: extract metadata, split, check duplicates, store."""

        extractor = MetadataExtractor()
        doc_meta = extractor.extract_document(text)
        meta = doc_meta.get("metadata", {})
        body_text = doc_meta.get("body_text", "")

        source_label = self._build_source_label(meta)

        if collection_type == "law":
            collection = self.law_collection
        else:
            collection = self.knowledge_collection

        # Duplicate check 1: exact source label match
        existing_count = self.vector_db.count_by_source(collection, source_label)
        if existing_count > 0:
            return {
                "status": "duplicate",
                "source": source_label,
                "existing_chunks": existing_count,
                "chunks": 0,
            }

        # Duplicate check 2: content similarity (catches old-format sources)
        sample_text = (body_text or text).strip()[:2000]
        is_dup, matched_source = self.vector_db.find_duplicate_by_content(
            collection, sample_text, threshold=0.80
        )
        if is_dup and matched_source:
            matched_count = self.vector_db.count_by_source(collection, matched_source)
            return {
                "status": "duplicate",
                "source": source_label,
                "matched_source": matched_source,
                "existing_chunks": matched_count,
                "chunks": 0,
            }

        # Split using same strategy as analysis pipeline
        text_for_split = body_text if body_text else text
        all_chunks = self.splitter.split_recursive(text_for_split, max_chunk_size=4000)

        chunk_texts = []
        metadatas = []
        ids = []

        for i, chunk_data in enumerate(all_chunks):
            chunk_text = chunk_data["text"] if isinstance(chunk_data, dict) else str(chunk_data)
            chunk_text = chunk_text.strip()
            if not chunk_text:
                continue

            # Extract Điều from chunk content
            match = re.search(r"(Điều\s+\d+)", chunk_text, re.IGNORECASE)
            article = match.group(1) if match else ""

            chunk_texts.append(chunk_text)
            metadatas.append({
                "source": source_label,
                "article": article,
                "chunk_id": i,
                "issuer": meta.get("issuer", ""),
                "so_van_ban": meta.get("so_van_ban", ""),
            })
            ids.append(f"{collection_type}_{uuid.uuid4()}")

        if not chunk_texts:
            return {"status": "empty", "source": source_label, "chunks": 0}

        self.vector_db.add_documents(
            chunk_texts,
            metadatas,
            ids,
            collection
        )

        return {
            "status": "success",
            "source": source_label,
            "chunks": len(chunk_texts),
            "metadata": meta,
        }

    def list_ingested(self, collection_type="law"):
        """List all unique sources in a collection."""
        collection = self.law_collection if collection_type == "law" else self.knowledge_collection
        sources = self.vector_db.list_sources(collection)
        result = []
        for src in sources:
            count = self.vector_db.count_by_source(collection, src)
            result.append({"source": src, "chunks": count})
        return result

    def delete_ingested(self, source, collection_type="law"):
        """Delete all chunks for a given source."""
        collection = self.law_collection if collection_type == "law" else self.knowledge_collection
        deleted = self.vector_db.delete_by_source(collection, source)
        return {"status": "deleted", "source": source, "deleted_chunks": deleted}

    # --------------------------------------------------
    # 2. LEGAL QUESTION ANSWERING
    # --------------------------------------------------

    def ask_legal_question(self, question):

        context = self.rag_engine.retrieve_context(question)

        if not context or context.strip() == "":
            return {
                "answer": "Không tìm thấy thông tin liên quan trong cơ sở dữ liệu. Vui lòng thử câu hỏi khác hoặc nạp thêm dữ liệu.",
                "context": "",
                "has_context": False,
            }

        prompt = PromptManager.build_qa_prompt(question, context)
        raw_answer = self.llm_agent.generate(prompt)

        # Sanitize: remove markdown artifacts, English noise
        answer = self.llm_agent._sanitize_prompt_artifacts(raw_answer)
        if self.llm_agent._contains_english(answer) and len(answer) > 100:
            # Retry once if mostly English
            answer = self.llm_agent.generate(prompt)
            answer = self.llm_agent._sanitize_prompt_artifacts(answer)

        return {
            "answer": answer,
            "context": context,
            "has_context": True,
        }

    # --------------------------------------------------
    # 3. USER DOCUMENT ANALYSIS
    # --------------------------------------------------

    def analyze_user_document(self, text):

        # 1) lấy thông tin metadata và xác định "căn cứ"
        extractor = MetadataExtractor()
        doc_meta = extractor.extract_document(text)
        can_cu_text = doc_meta.get("metadata", {}).get("can_cu", "")
        body_text = doc_meta.get("body_text", "")

        text_for_split = body_text if body_text else text

        all_chunks = self.splitter.split_recursive(text_for_split, max_chunk_size=4000)
        chunk_texts = [chunk["text"] for chunk in all_chunks]

        start_idx = 0
        if can_cu_text:
            for i, chunk_text in enumerate(chunk_texts):
                if can_cu_text.strip() and can_cu_text.strip() in chunk_text:
                    start_idx = min(i + 1, len(chunk_texts))
                    break
                # fallback: tìm câu chứa "Căn cứ" nếu không khớp chính xác
                if "căn cứ" in chunk_text.lower():
                    start_idx = min(i + 1, len(chunk_texts))
                    break

        # Chỉ xử lý từ chunk sau căn cứ trở đi
        working_chunks = chunk_texts[start_idx:]

        analysis = self.llm_agent.analyze_document(working_chunks, can_cu_text=can_cu_text)

        analysis_text = json.dumps(analysis, ensure_ascii=False, indent=2)

        can_cu_phap_ly = analysis.get("can_cu_phap_ly", [])

        query = " ; ".join(can_cu_phap_ly).strip()
        if not query:
            # fallback: build query from nhiem_vu summaries
            nhiem_vu = analysis.get("nhiem_vu", [])
            parts = [t.get("noi_dung", "") for t in nhiem_vu if t.get("noi_dung")]
            query = " ; ".join(parts)[:300] if parts else analysis.get("tom_tat", "")[:300]

        context = self.rag_engine.retrieve_context(query)

        if context:
            suggestion_prompt = PromptManager.build_suggestion_prompt(
                analysis_text,
                context
            )
            raw_output = self.llm_agent.generate(suggestion_prompt)

            try:
                json_str = re.search(r"\{.*\}", raw_output, re.DOTALL).group()
                suggestions = json.loads(json_str)
            except Exception:
                suggestions = {
                    "raw_text": raw_output
                }
        else:
            suggestions = {
                "can_cu_phap_ly": can_cu_phap_ly,
                "risks": [],
                "recommendations": []
            }

        # Human-readable summary
        summary_prompt = PromptManager.build_readable_summary_prompt(analysis)
        readable_summary = self.llm_agent.generate(summary_prompt)

        return {
            "analysis": analysis,
            "document_metadata": doc_meta.get("metadata", {}),
            "analysis_readable": readable_summary,
            "related_context": context,
            "suggestions": suggestions
        }
    