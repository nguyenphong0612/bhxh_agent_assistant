import json
import re
from typing import Dict
from Document_processing.splitter import TextSplitter


class MetadataExtractor:
    def __init__(self, model=None):
        self._model = model

     # =====================================================
    # =============== DOCUMENT LEVEL =======================
    # =====================================================

    def extract_document(self, text: str) -> Dict:
        # Plain text (no markdown markers) for metadata extraction
        text_plain = self._strip_md_markers(text)
        clean_meta = self._remove_quoc_hieu(text_plain)

        issuer = self._extract_issuer(clean_meta)
        doc_info = self._extract_document_number(clean_meta)
        title = self._extract_title(clean_meta)
        can_cu = self._extract_can_cu(clean_meta)

        # Original markdown for body text detection (needs # markers)
        clean_text = self._remove_quoc_hieu(text)
        body_text = self._strip_metadata_blocks(clean_text)

        return {
            "metadata": {
                "issuer": issuer,
                "so_van_ban": doc_info["so_van_ban"],
                "ngay_ban_hanh": doc_info["ngay_ban_hanh"],
                "tieu_de": title,
                "can_cu": can_cu
            },
            "clean_text": clean_text,
            "body_text": body_text
        }

    def _strip_md_markers(self, text: str) -> str:
        """Strip markdown formatting markers for metadata extraction."""
        cleaned = []
        for line in text.split('\n'):
            line = re.sub(r'^>\s*', '', line)       # blockquote
            line = re.sub(r'^#{1,6}\s*', '', line)  # heading
            line = line.replace('*', '')              # bold/italic
            cleaned.append(line)
        return '\n'.join(cleaned)

    def _remove_quoc_hieu(self, text: str) -> str:
        return re.sub(
            r"\*{0,2}CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\*{0,2}.*?Hạnh phúc",
            "",
            text,
            flags=re.IGNORECASE | re.DOTALL
        )

    def _normalized_lines(self, text: str, keep_empty: bool = False):
        normalized = [re.sub(r"\s+", " ", line).strip() for line in text.split("\n")]
        if keep_empty:
            return normalized
        return [line for line in normalized if line]

    def _extract_issuer(self, text: str) -> str:
        lines = self._normalized_lines(text)

        doc_idx = -1
        for i, line in enumerate(lines[:20]):
            if re.search(r"^số\s*:|^\d{1,6}\s*/\s*[A-ZĐ\-]+|^/[A-ZĐ\-]+", line, re.IGNORECASE):
                doc_idx = i
                break

        search_end = doc_idx if doc_idx != -1 else min(len(lines), 12)
        header_lines = lines[:search_end]

        org_lines = []
        for line in header_lines:
            if re.search(r"(CỘNG HÒA|Độc lập|Hạnh phúc|Kính gửi|ngày\s+\d{1,2}\s+tháng)", line, re.IGNORECASE):
                continue
            if re.search(r"\b(BỘ|BHXH|BẢO HIỂM XÃ HỘI|UBND|SỞ|CỤC|BAN)\b", line, re.IGNORECASE):
                org_lines.append(line)

        if not org_lines:
            return ""

        # Keep compact issuer name from top block.
        if len(org_lines) >= 2 and len(org_lines[0]) <= 25 and len(org_lines[1]) <= 80:
            return f"{org_lines[0]} {org_lines[1]}".strip()
        return org_lines[0].strip()

    def _extract_document_number(self, text: str) -> Dict:
        lines = self._normalized_lines(text)

        so_van_ban = ""

        # Case 1: full form in one line: "Số: 1584/BHXH-QLT"
        for i, line in enumerate(lines[:20]):
            match_full = re.search(r"số\s*:\s*(\d{1,6})\s*/\s*([A-ZĐ\-]+)", line, re.IGNORECASE)
            if match_full:
                so_van_ban = f"{match_full.group(1)}/{match_full.group(2)}"
                break

            # Case 2: split lines: "Số:" then "1584" then "/BHXH-QLT"
            if re.match(r"^số\s*:?$", line, re.IGNORECASE):
                next1 = lines[i + 1] if i + 1 < len(lines) else ""
                next2 = lines[i + 2] if i + 2 < len(lines) else ""
                m_num = re.search(r"(\d{1,6})", next1)
                m_code = re.search(r"/?\s*([A-ZĐ\-]{3,})", next2)
                if m_num and m_code:
                    so_van_ban = f"{m_num.group(1)}/{m_code.group(1)}"
                    break

        ngay = re.search(
            r"ngày\s+\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+\d{4}",
            text,
            re.IGNORECASE
        )

        return {
            "so_van_ban": so_van_ban,
            "ngay_ban_hanh": ngay.group() if ngay else ""
        }

    def _extract_title(self, text: str) -> str:
        lines = self._normalized_lines(text)

        # Anchor title extraction after header lines that contain document number and issue date.
        # Limit to first 12 lines — header area only, avoid matching doc numbers in body.
        anchor_idx = -1
        for i, line in enumerate(lines[:12]):
            if re.search(r"^số\s*:|^\d{1,6}\s*/\s*[A-ZĐ\-]+|^/[A-ZĐ\-]+", line, re.IGNORECASE):
                anchor_idx = max(anchor_idx, i)
            if re.search(r"\bngày\s+\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+\d{4}\b", line, re.IGNORECASE):
                anchor_idx = max(anchor_idx, i)

        start_index = anchor_idx + 1 if anchor_idx >= 0 else 0

        # Fallback: if no anchor found, seek the first V/v line near the top.
        if start_index == 0:
            for i, line in enumerate(lines[:20]):
                if re.search(r"^(v/v|về)\b", line, re.IGNORECASE):
                    start_index = i
                    break

        stop_pattern = re.compile(
            r"^(kính gửi\s*:|căn\s+cứ\b|nơi nhận\s*:|phạm vi\b|điều\s+\d+\b)",
            re.IGNORECASE,
        )

        title_lines = []
        collecting = False
        for line in lines[start_index:start_index + 12]:
            if stop_pattern.search(line):
                break

            if not collecting:
                if re.search(r"^(v/v|về)\b", line, re.IGNORECASE):
                    collecting = True
                    title_lines.append(line)
                continue

            # Keep short continuation lines of title; stop before body content.
            if len(line) <= 140:
                title_lines.append(line)
            else:
                break

        title = " ".join(title_lines).strip()
        title = re.sub(r"\s+", " ", title)
        return title

    def _extract_can_cu(self, text: str) -> str:
        lines = self._normalized_lines(text)
        start_idx = -1
        for i, line in enumerate(lines):
            if re.search(r"^căn\s+cứ\b", line, re.IGNORECASE):
                start_idx = i
                break

        if start_idx == -1:
            return ""

        stop_pattern = re.compile(
            r"^(?:kính gửi\s*:|phạm vi\b|nội dung\b|điều\s+\d+\b|mục\s+[ivxlc]+\b|chương\s+[ivxlc]+\b|phần\s+[ivxlc]+\b|[ivxlc]+[\.\)]\b|[A-Z][\.\)\-:]\b|\d+\.\d+\b|\d+\.)",
            re.IGNORECASE,
        )

        collected = [lines[start_idx]]
        for line in lines[start_idx + 1:]:
            if stop_pattern.search(line):
                break
            collected.append(line)

        can_cu = " ".join(collected).strip()
        can_cu = re.sub(r"\s+", " ", can_cu)
        return can_cu

    def _find_title_span(self, lines):
        anchor_idx = -1
        for i, line in enumerate(lines[:12]):
            if re.search(r"^số\s*:|^\d{1,6}\s*/\s*[A-ZĐ\-]+|^/[A-ZĐ\-]+", line, re.IGNORECASE):
                anchor_idx = max(anchor_idx, i)
            if re.search(r"\bngày\s+\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+\d{4}\b", line, re.IGNORECASE):
                anchor_idx = max(anchor_idx, i)

        start_index = anchor_idx + 1 if anchor_idx >= 0 else 0
        if start_index == 0:
            for i, line in enumerate(lines[:20]):
                if re.search(r"^(v/v|về)\b", line, re.IGNORECASE):
                    start_index = i
                    break

        stop_pattern = re.compile(
            r"^(kính gửi\s*:|căn\s+cứ\b|nơi nhận\s*:|phạm vi\b|điều\s+\d+\b)",
            re.IGNORECASE,
        )

        start = -1
        end = -1
        collecting = False
        for i in range(start_index, min(start_index + 12, len(lines))):
            line = lines[i]
            if stop_pattern.search(line):
                break
            if not collecting:
                if re.search(r"^(v/v|về)\b", line, re.IGNORECASE):
                    collecting = True
                    start = i
                    end = i
                continue
            if len(line) <= 140:
                end = i
            else:
                break
        return start, end

    def _find_can_cu_span(self, lines):
        start_idx = -1
        for i, line in enumerate(lines):
            if re.search(r"^căn\s+cứ\b", line, re.IGNORECASE):
                start_idx = i
                break

        if start_idx == -1:
            return -1, -1

        stop_pattern = re.compile(
            r"^(?:kính gửi\s*:|phạm vi\b|nội dung\b|điều\s+\d+\b|mục\s+[ivxlc]+\b|chương\s+[ivxlc]+\b|phần\s+[ivxlc]+\b|[ivxlc]+[\.\)]\b|[A-Z][\.\)\-:]\b|\d+\.\d+\b|\d+\.)",
            re.IGNORECASE,
        )

        end_idx = start_idx
        for i in range(start_idx + 1, len(lines)):
            if stop_pattern.search(lines[i]):
                break
            end_idx = i

        return start_idx, end_idx

    def _strip_metadata_blocks(self, text: str) -> str:
        """
        Remove header metadata blocks.
        
        Strategy for markdown (from pypandoc):
        1. Find first content heading (# with ilvl, not decorative like 'Độc lập...')
        2. Everything before that heading is header → strip metadata from it
        3. Return from first content heading onward as body_text
        """
        raw_lines = text.split("\n")
        lines = self._normalized_lines(text, keep_empty=True)
        if not raw_lines:
            return ""

        # For markdown: find first real content heading
        # Skip decorative headings (quốc hiệu, empty headings)
        skip_headings = {'độc lập - tự do - hạnh phúc', ''}
        body_start_line_idx = len(raw_lines)
        
        for idx, raw_line in enumerate(raw_lines):
            if raw_line.startswith('#'):
                htext = raw_line.lstrip('#').strip()
                if htext.lower() not in skip_headings:
                    body_start_line_idx = idx
                    break

        # If no markdown heading found, fallback to pattern-based detection
        if body_start_line_idx == len(raw_lines):
            try:
                splitter = TextSplitter()
                pattern_position = splitter.find_first_priority_pattern_position(text)
                char_count = 0
                for idx in range(len(raw_lines)):
                    line_end_pos = char_count + len(raw_lines[idx]) + 1
                    if char_count <= pattern_position < line_end_pos:
                        body_start_line_idx = idx
                        break
                    char_count = line_end_pos
            except:
                pass

        # Body = everything from body_start_line_idx onward
        remaining = []
        for idx in range(body_start_line_idx, len(raw_lines)):
            raw_line = raw_lines[idx]
            if not raw_line.strip():
                continue
            remaining.append(raw_line)

        return "\n".join(remaining).strip()

    # =========================
    # 1. PROMPT
    # =========================
    def _build_prompt(self, text: str) -> str:
        return f"""
Bạn là hệ thống trích xuất thông tin từ văn bản hành chính tiếng Việt.

Nhiệm vụ:
Trích xuất thông tin vào JSON theo schema:

{{
  "noi_dung": "mục tiêu hoặc hành động chính",
  "so_luong": "các con số, tỷ lệ nếu có",
  "thoi_gian_bat_dau": "dd/mm/yyyy nếu có thể",
  "thoi_han": "thời lượng hoặc deadline",
  "phu_trach": "đơn vị chịu trách nhiệm chính",
  "kinh_phi": "nguồn hoặc mức kinh phí",
  "luc_luong_phoi_hop": "đơn vị phối hợp",
  "dia_diem": "nơi thực hiện"
}}

QUY TẮC BẮT BUỘC:
- Chỉ lấy thông tin có trong văn bản
- Không suy diễn
- Không thêm thông tin ngoài văn bản
- Nếu không có → ghi "không nói rõ"
- Trả về JSON hợp lệ, KHÔNG giải thích

------------------------
VÍ DỤ:

Input:
"...từ ngày 1/4/2026 các cơ quan BHXH cấp xã tổ chức thực hiện, trong vòng 1 tháng phải tăng 10% đối tượng tự nguyện..."

Output:
{{
  "noi_dung": "tăng số lượng đối tượng tham gia BHXH",
  "so_luong": "10% tự nguyện",
  "thoi_gian_bat_dau": "01/04/2026",
  "thoi_han": "1 tháng",
  "phu_trach": "cơ quan BHXH cấp xã",
  "kinh_phi": "không nói rõ",
  "luc_luong_phoi_hop": "không nói rõ",
  "dia_diem": "không nói rõ"
}}

------------------------

Văn bản:
\"\"\"
{text}
\"\"\"

Trả về JSON:
""".strip()

    # =========================
    # 2. CALL LLM
    # =========================
    def _get_model(self):
        if self._model is None:
            from Config.model_provider import create_model
            self._model = create_model()
        return self._model

    def _call_llm(self, prompt: str) -> str:
        return self._get_model().generate(prompt)

    # =========================
    # 3. EXTRACT JSON
    # =========================
    def _extract_json(self, text: str):
        try:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception:
            return None
        return None

    # =========================
    # 4. NORMALIZE
    # =========================
    def _normalize(self, data: dict) -> dict:
        keys = [
            "noi_dung",
            "so_luong",
            "thoi_gian_bat_dau",
            "thoi_han",
            "phu_trach",
            "kinh_phi",
            "luc_luong_phoi_hop",
            "dia_diem"
        ]

        for k in keys:
            if k not in data or not data[k]:
                data[k] = "không nói rõ"

        return data

    # =========================
    # 5. MAIN FUNCTION
    # =========================
    def extract(self, text: str, max_retry: int = 3) -> dict:
    # 🔥 lấy metadata document-level trước
        doc_meta = self.extract_document(text)["metadata"]

        prompt = self._build_prompt(text)

        for i in range(max_retry):
            try:
                raw_output = self._call_llm(prompt)
                data = self._extract_json(raw_output)

                if data:
                    data = self._normalize(data)

                    # 🔥 merge vào đây
                    data.update({
                        "so_van_ban": doc_meta.get("so_van_ban", "không nói rõ"),
                        "ngay_ban_hanh": doc_meta.get("ngay_ban_hanh", "không nói rõ"),
                        "tieu_de": doc_meta.get("tieu_de", "không nói rõ"),
                        "co_quan_ban_hanh": doc_meta.get("issuer", "không nói rõ"),
                    })

                    return data

            except Exception as e:
                print(f"⚠️ Extract lỗi lần {i+1}: {e}")

        # fallback
        return {
            "noi_dung": "không nói rõ",
            "so_luong": "không nói rõ",
            "thoi_gian_bat_dau": "không nói rõ",
            "thoi_han": "không nói rõ",
            "phu_trach": "không nói rõ",
            "kinh_phi": "không nói rõ",
            "luc_luong_phoi_hop": "không nói rõ",
            "dia_diem": "không nói rõ",
            "so_van_ban": "không nói rõ",
            "ngay_ban_hanh": "không nói rõ",
            "tieu_de": "không nói rõ",
            "co_quan_ban_hanh": "không nói rõ"
        }