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
    def build_suggestion_prompt(analysis, context):
        context_text = context if isinstance(context, str) else PromptManager.format_context(context)
        prompt = f"""
Bạn là chuyên gia pháp lý Việt Nam.

Nhiệm vụ: dựa CHỈ trên phân tích tài liệu và ngữ cảnh pháp lý được cung cấp, trả về JSON đề xuất hành động.

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
  "khuyen_nghi": ["khuyến nghị 1", "khuyến nghị 2"]
}}

VÍ DỤ:
Nếu tài liệu cho thấy doanh nghiệp chậm đóng bảo hiểm xã hội và context nêu nghĩa vụ khắc phục, kết quả hợp lệ là:
{{
  "can_cu_phap_ly": ["Luật Bảo hiểm xã hội 2014"],
  "khuyen_nghi": ["đối chiếu số tiền còn thiếu và lập kế hoạch khắc phục ngay"]
}}

PHÂN TÍCH TÀI LIỆU:
{analysis}

NGỮ CẢNH PHÁP LÝ LIÊN QUAN:
{context_text}

JSON:
"""
        return prompt

