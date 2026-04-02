import streamlit as st
import json
import tempfile
import os
from datetime import datetime
from Core.workflow import LegalAgentWorkflow
from Document_processing.loader import DocumentLoader
from Config.setting import FEEDBACK_FILE
from Config.model_provider import create_model

def format_analysis(analysis):
    """Format analysis result (new schema) thành list dễ đọc."""
    lines = []
    idx = 1

    # Nhiệm vụ
    nhiem_vu = analysis.get("nhiem_vu", [])
    if nhiem_vu:
        lines.append(f"{idx}. Nhiệm vụ các đơn vị:")
        idx += 1
        for t in nhiem_vu:
            don_vi = t.get("don_vi", "?")
            vai_tro = t.get("vai_tro", "")
            noi_dung = t.get("noi_dung", "")
            line = f"   - {don_vi}"
            if vai_tro:
                line += f" ({vai_tro})"
            if noi_dung:
                line += f": {noi_dung}"
            lines.append(line)

    # Quy trình thực hiện
    quy_trinh = analysis.get("quy_trinh", [])
    if quy_trinh:
        lines.append(f"{idx}. Quy trình thực hiện:")
        idx += 1
        for step in quy_trinh:
            b = step.get("buoc", "?")
            hd = step.get("hanh_dong", "")
            dv = step.get("don_vi", "")
            line = f"   **Bước {b}**: {hd}"
            if dv:
                line += f" — *{dv}*"
            lines.append(line)

    # Thời gian
    thoi_gian = analysis.get("thoi_gian", "không nói rõ")
    if thoi_gian and thoi_gian != "không nói rõ":
        lines.append(f"{idx}. Thời gian: {thoi_gian}")
        idx += 1

    # Kinh phí
    kinh_phi = analysis.get("kinh_phi", "không nói rõ")
    if kinh_phi and kinh_phi != "không nói rõ":
        lines.append(f"{idx}. Kinh phí: {kinh_phi}")
        idx += 1

    # Địa điểm
    dia_diem = analysis.get("dia_diem", "không nói rõ")
    if dia_diem and dia_diem != "không nói rõ":
        lines.append(f"{idx}. Địa điểm: {dia_diem}")
        idx += 1

    # Căn cứ pháp lý
    can_cu = analysis.get("can_cu_phap_ly", [])
    if can_cu:
        lines.append(f"{idx}. Căn cứ pháp lý: {', '.join(can_cu)}")
        idx += 1

    # Lưu ý
    luu_y = analysis.get("luu_y", "")
    if luu_y and luu_y != "không có":
        lines.append(f"{idx}. Lưu ý: {luu_y}")
        idx += 1

    # Tóm tắt
    tom_tat = analysis.get("tom_tat", "")
    if tom_tat:
        lines.append(f"{idx}. Tóm tắt: {tom_tat}")
        idx += 1

    return "\n".join(lines)

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

            st.subheader("� Thông tin văn bản")
            doc_meta = result.get("document_metadata", {})
            if doc_meta:
                for k, v in doc_meta.items():
                    if v and k != "can_cu":
                        st.write(f"**{k}:** {v}")

            st.subheader("📝 Phân tích (Dễ đọc)")
            formatted = format_analysis(result["analysis"])
            if formatted:
                st.markdown(formatted)
            else:
                st.code(result.get("analysis_readable", "Không có"), language="text")

            st.subheader("📄 Phân tích (JSON)")
            st.json(result["analysis"])

            st.subheader("⚠️ Đề xuất & Rủi ro")
            st.json(result["suggestions"])
    
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
                st.json(result)

# ==============================
# TAB 4 — Feedback Logs
with tab4:
    st.header("Feedback logs")

    try:
        with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            st.json(data)
    except:
        st.write("Chưa có feedback")