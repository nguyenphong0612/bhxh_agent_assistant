import streamlit as st
import json
import tempfile
import os
from datetime import datetime
from Core.workflow import LegalAgentWorkflow
from Document_processing.loader import DocumentLoader
from Config.setting import FEEDBACK_FILE
from Config.model_provider import create_model


def _render_main_summary(analysis):
    """Render mục 1: tóm tắt ngắn gọn cho người dùng."""
    tom_tat = (analysis or {}).get("tom_tat", "")
    if tom_tat:
        st.markdown(tom_tat)
    else:
        st.info("Chưa có tóm tắt.")


def _render_process_steps(analysis):
    """Render mục 2: quy trình các bước thực hiện."""
    quy_trinh = (analysis or {}).get("quy_trinh", [])
    if not quy_trinh:
        st.info("Chưa trích xuất được quy trình.")
        return

    for step in quy_trinh:
        buoc = step.get("buoc", "?")
        hanh_dong = step.get("hanh_dong", "")
        don_vi = step.get("don_vi", "")

        if don_vi:
            st.markdown(f"**Bước {buoc}.** {hanh_dong}  ")
            st.caption(f"Đơn vị: {don_vi}")
        else:
            st.markdown(f"**Bước {buoc}.** {hanh_dong}")


def _render_related_info(result):
    """Render mục 3: thông tin liên quan (thu gọn để đỡ rối mắt)."""
    analysis = result.get("analysis", {}) if isinstance(result, dict) else {}
    doc_meta = result.get("document_metadata", {}) if isinstance(result, dict) else {}
    suggestions = result.get("suggestions", {}) if isinstance(result, dict) else {}

    with st.expander("Mở thông tin liên quan"):
        # Thông tin văn bản
        if doc_meta:
            st.markdown("**Thông tin văn bản**")
            for k, v in doc_meta.items():
                if v:
                    st.write(f"- {k}: {v}")

        # Nhiệm vụ
        nhiem_vu = analysis.get("nhiem_vu", [])
        if nhiem_vu:
            st.markdown("**Nhiệm vụ các đơn vị**")
            for task in nhiem_vu:
                don_vi = task.get("don_vi", "?")
                vai_tro = task.get("vai_tro", "")
                noi_dung = task.get("noi_dung", "")
                line = f"- {don_vi}"
                if vai_tro:
                    line += f" ({vai_tro})"
                if noi_dung:
                    line += f": {noi_dung}"
                st.write(line)

        # Các trường thông tin còn lại
        for label, key in [
            ("Thời gian", "thoi_gian"),
            ("Kinh phí", "kinh_phi"),
            ("Địa điểm", "dia_diem"),
            ("Lưu ý", "luu_y"),
        ]:
            value = analysis.get(key)
            if value and value not in ["không nói rõ", "không có"]:
                st.write(f"- {label}: {value}")

        can_cu = analysis.get("can_cu_phap_ly", [])
        if can_cu:
            st.markdown("**Căn cứ pháp lý (phân tích)**")
            for item in can_cu:
                st.write(f"- {item}")

        # Đề xuất tham khảo
        khuyen_nghi = suggestions.get("khuyen_nghi", [])
        can_cu_goi_y = suggestions.get("can_cu_phap_ly", [])
        if khuyen_nghi or can_cu_goi_y:
            st.markdown("**Đề xuất tham khảo**")
            if can_cu_goi_y:
                st.markdown("Căn cứ pháp lý:")
                for item in can_cu_goi_y:
                    st.write(f"- {item}")
            if khuyen_nghi:
                st.markdown("Khuyến nghị:")
                for item in khuyen_nghi:
                    st.write(f"- {item}")

def save_feedback(data):
    try:
        with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
            feedbacks = json.load(f)
    except:
        feedbacks = []

    feedbacks.append(data)

    with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
        json.dump(feedbacks, f, ensure_ascii=False, indent=2)


# ---- Init
model = create_model()
workflow = LegalAgentWorkflow(model)
doc_loader = DocumentLoader()


# ---- UI
st.title("⚖️ Legal Agent Assistant")

tab1, tab2, tab3, tab4 = st.tabs([
    "Hỏi/Đáp pháp luật",
    "Phân tích tài liệu",
    "Nạp dữ liệu",
    "Feedback"
])


# ==============================
# TAB 1 — Q&A
# ==============================
with tab1:
    st.header("Hỏi/Đáp pháp luật")

    question = st.text_input("Nhập câu hỏi:")

    
    if "last_qa" not in st.session_state:
        st.session_state.last_qa = {}

    if st.button("Trả lời"):
        if question:
            with st.spinner("Đang tìm kiếm và trả lời..."):
                result = workflow.ask_legal_question(question)

            answer_text = result.get("answer", "") if isinstance(result, dict) else str(result)
            has_context = result.get("has_context", True) if isinstance(result, dict) else True

            if not has_context:
                st.warning(answer_text)
            else:
                st.markdown(answer_text)

            # Show retrieved context in expander
            if isinstance(result, dict) and result.get("context"):
                with st.expander("📚 Ngữ cảnh tham chiếu"):
                    st.code(result["context"], language="text")

            st.session_state.last_qa = {
                "question": question,
                "answer": answer_text
            }

    # Feedback buttons
    if st.session_state.last_qa:
        col1, col2 = st.columns(2)

        with col1:
            if st.button("👍 Hữu ích"):
                save_feedback({
                    **st.session_state.last_qa,
                    "feedback": "positive",
                    "time": str(datetime.now())
                })
                st.success("Đã lưu feedback")

        with col2:
            if st.button("👎 Không đúng"):
                save_feedback({
                    **st.session_state.last_qa,
                    "feedback": "negative",
                    "time": str(datetime.now())
                })
                st.warning("Đã lưu feedback")
# ==============================
# TAB 2 — Document Analysis
# ==============================
with tab2:
    st.header("Phân tích tài liệu")

    uploaded_file = st.file_uploader("Upload file (.txt hoặc .docx)", type=["txt", "docx"], key="analyze")

    if uploaded_file:
        # Load file content using DocumentLoader for proper .docx support
        if uploaded_file.name.endswith(".docx"):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
                tmp.write(uploaded_file.read())
                tmp_path = tmp.name
            text = doc_loader.load(tmp_path)
            os.unlink(tmp_path)
        else:
            text = uploaded_file.read().decode("utf-8")

        if st.button("Phân tích"):
            result = workflow.analyze_user_document(text)

            analysis = result.get("analysis", {})

            st.subheader("1) Tóm tắt")
            _render_main_summary(analysis)

            st.subheader("2) Quy trình các bước thực hiện")
            _render_process_steps(analysis)

            st.subheader("3) Các thông tin liên quan")
            _render_related_info(result)
    
# ==============================
# TAB 3 — Ingest Document
with tab3:
    st.header("Nạp dữ liệu (Ingest)")

    collection_type = st.selectbox(
        "Chọn loại dữ liệu",
        ["law", "knowledge"]
    )

    # --- Section 1: Existing documents ---
    st.subheader("📂 Dữ liệu đã nạp")
    ingested = workflow.list_ingested(collection_type)
    if ingested:
        for item in ingested:
            col_src, col_cnt, col_del = st.columns([6, 1, 1])
            with col_src:
                st.write(item["source"])
            with col_cnt:
                st.write(f"{item['chunks']} chunks")
            with col_del:
                if st.button("🗑️", key=f"del_{hash(item['source'])}"):
                    del_result = workflow.delete_ingested(item["source"], collection_type)
                    st.success(f"Đã xóa {del_result['deleted_chunks']} chunks")
                    st.rerun()
    else:
        st.info("Chưa có dữ liệu nào.")

    # --- Section 2: Upload & Preview ---
    st.subheader("📤 Nạp văn bản mới")
    uploaded_file = st.file_uploader("Upload file (.txt hoặc .docx)", type=["txt", "docx"], key="ingest")

    if uploaded_file:
        if uploaded_file.name.endswith(".docx"):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
                tmp.write(uploaded_file.read())
                tmp_path = tmp.name
            text = doc_loader.load(tmp_path)
            os.unlink(tmp_path)
        else:
            text = uploaded_file.read().decode("utf-8")

        # Preview
        preview = workflow.ingest_preview(text)
        meta = preview.get("metadata", {})

        st.markdown(f"**Nguồn:** {preview['source_label']}")
        if meta.get("issuer"):
            st.markdown(f"**Cơ quan ban hành:** {meta['issuer']}")
        if meta.get("ngay_ban_hanh"):
            st.markdown(f"**Ngày ban hành:** {meta['ngay_ban_hanh']}")
        st.markdown(f"**Số chunks:** {preview['chunk_count']}")

        with st.expander(f"Xem trước chunks ({preview['chunk_count']})"):
            for i, chunk in enumerate(preview["chunks"]):
                chunk_text = chunk["text"] if isinstance(chunk, dict) else str(chunk)
                st.text(f"[{i}] ({len(chunk_text)} chars) {chunk_text[:120]}...")

        if st.button("Nạp vào hệ thống"):
            with st.spinner("Đang xử lý..."):
                result = workflow.ingest_document(text, collection_type=collection_type)

            if result["status"] == "success":
                st.success(f"Đã thêm {result['chunks']} chunks vào {collection_type}: {result['source']}")
            elif result["status"] == "duplicate":
                msg = f"Văn bản đã tồn tại ({result['existing_chunks']} chunks): {result['source']}"
                if result.get("matched_source"):
                    msg += f"\n\n*Trùng nội dung với:* {result['matched_source'][:100]}"
                st.warning(msg)
            elif result["status"] == "empty":
                st.error("Không tách được chunk nào từ văn bản.")
            else:
                st.error("Có lỗi khi nạp dữ liệu. Vui lòng thử lại.")
                st.caption(str(result))

# ==============================
# TAB 4 — Feedback Logs
with tab4:
    st.header("Feedback logs")

    try:
        with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not data:
                st.write("Chưa có feedback")
            else:
                for i, item in enumerate(reversed(data), start=1):
                    q = item.get("question", "")
                    a = item.get("answer", "")
                    fb = item.get("feedback", "")
                    t = item.get("time", "")
                    with st.expander(f"#{i} - {fb} - {t}"):
                        st.markdown(f"**Câu hỏi:** {q}")
                        st.markdown(f"**Trả lời:** {a}")
    except:
        st.write("Chưa có feedback")