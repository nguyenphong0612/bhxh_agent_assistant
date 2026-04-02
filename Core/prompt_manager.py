class PromptManager:

    @staticmethod
    def format_context(context):
        """Accept either a pre-formatted string or a list of docs."""
        if not context:
            return "Không có thông tin liên quan."
        if isinstance(context, str):
            return context
        formatted = []
        for i, doc in enumerate(context, 1):
            formatted.append(f"[Tài liệu {i}]\n{doc}")
        return "\n\n".join(formatted)

    @staticmethod
    def build_qa_prompt(question, context):
        context_text = context if isinstance(context, str) else PromptManager.format_context(context)
        prompt = f"""Bạn là trợ lý pháp luật Việt Nam.

NHIỆM VỤ: Trả lời câu hỏi pháp luật dựa CHỈ trên ngữ cảnh được cung cấp.

QUY TẮC BẮT BUỘC:
1. Chỉ dùng tiếng Việt.
2. Chỉ trả lời dựa trên ngữ cảnh bên dưới. Không suy đoán ngoài dữ liệu.
3. Nếu ngữ cảnh không đủ → nói rõ: "Không đủ thông tin trong dữ liệu hiện có để trả lời."
4. Khi trích dẫn pháp lý, lấy nguồn từ ngữ cảnh (ví dụ: [LUẬT - Điều X]).
5. Không được tự tạo nguồn mới hoặc suy đoán tên luật.
6. Không dùng markdown tiêu đề (#). Không dùng tiếng Anh.

CÂU HỎI:
{question}

NGỮ CẢNH:
{context_text}

ĐỊNH DẠNG TRẢ LỜI:
1. Trả lời ngắn gọn: (1-2 câu tóm tắt)
2. Giải thích chi tiết: (phân tích cụ thể dựa trên ngữ cảnh)
3. Căn cứ pháp lý: (liệt kê nguồn từ ngữ cảnh, nếu có)

TRẢ LỜI:"""
        return prompt

    @staticmethod
    def build_readable_summary_prompt(analysis):
        nhiem_vu = analysis.get("nhiem_vu", [])
        tasks_text = ""
        for t in nhiem_vu:
            line = f"- {t.get('don_vi', '?')}"
            if t.get("vai_tro"):
                line += f" ({t['vai_tro']})"
            if t.get("noi_dung"):
                line += f": {t['noi_dung']}"
            tasks_text += line + "\n"
        if not tasks_text:
            tasks_text = "Không rõ"

        quy_trinh = analysis.get("quy_trinh", [])
        quy_trinh_text = ""
        for step in quy_trinh:
            b = step.get("buoc", "?")
            hd = step.get("hanh_dong", "")
            dv = step.get("don_vi", "")
            quy_trinh_text += f"- Bước {b}: {hd}"
            if dv:
                quy_trinh_text += f" ({dv})"
            quy_trinh_text += "\n"

        thoi_gian = analysis.get("thoi_gian", "không nói rõ")
        kinh_phi = analysis.get("kinh_phi", "không nói rõ")
        dia_diem = analysis.get("dia_diem", "không nói rõ")
        can_cu = analysis.get("can_cu_phap_ly", [])
        can_cu_text = ", ".join(can_cu) if can_cu else "Không có"
        tom_tat = analysis.get("tom_tat", "")

        prompt = f"""Bạn là trợ lý pháp luật AI. Dựa trên phân tích dưới đây, tạo một tóm tắt dễ đọc cho người dùng không chuyên.

THÔNG TIN VỪA TRÍCH XUẤT:
Nhiệm vụ:
{tasks_text}
Quy trình thực hiện:
{quy_trinh_text if quy_trinh_text else 'Không có'}
Thời gian: {thoi_gian}
Kinh phí: {kinh_phi}
Địa điểm: {dia_diem}
Căn cứ pháp lý: {can_cu_text}

TÓM TẮT: {tom_tat}

Hãy tạo một bản tóm tắt dễ hiểu cho người dùng:
- Dùng tiếng Việt rõ ràng
- Chỉ 3-5 dòng chính
- Vắn tắt, không lặp lại
"""
        return prompt

    @staticmethod
    def build_suggestion_prompt(analysis, context):
        context_text = context if isinstance(context, str) else PromptManager.format_context(context)
        prompt = f"""
Bạn là chuyên gia pháp lý Việt Nam.

Nhiệm vụ: dựa CHỈ trên phân tích tài liệu và ngữ cảnh pháp lý được cung cấp, trả về JSON đánh giá rủi ro.

QUY TẮC BẮT BUỘC:
- Chỉ dùng tiếng Việt.
- Không dùng tiếng Anh.
- Không giải thích ngoài JSON.
- Không đặt lại câu hỏi.
- Không suy diễn ngoài dữ liệu đầu vào.
- Nếu không đủ dữ liệu ở trường nào thì trả về mảng rỗng cho trường đó.

ĐỊNH DẠNG JSON BẮT BUỘC:
{{
  "can_cu_phap_ly": ["căn cứ pháp lý 1", "căn cứ pháp lý 2"],
  "risks": ["rủi ro 1", "rủi ro 2"],
  "recommendations": ["khuyến nghị 1", "khuyến nghị 2"]
}}

VÍ DỤ:
Nếu tài liệu cho thấy doanh nghiệp chậm đóng bảo hiểm xã hội và context nêu nghĩa vụ khắc phục, kết quả hợp lệ là:
{{
  "can_cu_phap_ly": ["Luật Bảo hiểm xã hội 2014"],
  "risks": ["có thể bị yêu cầu truy nộp và xử lý vi phạm"],
  "recommendations": ["đối chiếu số tiền còn thiếu và lập kế hoạch khắc phục ngay"]
}}

PHÂN TÍCH TÀI LIỆU:
{analysis}

NGỮ CẢNH PHÁP LÝ LIÊN QUAN:
{context_text}

JSON:
"""
        return prompt