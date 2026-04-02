import json
import re


class LLMAgent:

    def __init__(self, model):
        self.model = model
        self.max_chunks = 40
        self.editorial_group_size = 6

    def generate(self, prompt):
        response = self.model.generate(prompt)
        if isinstance(response, str):
            return response.strip()
        return str(response)

    def _empty_metadata(self):
        return {
            "nhiem_vu": [],
            "quy_trinh": [],
            "thoi_gian": "không nói rõ",
            "kinh_phi": "không nói rõ",
            "dia_diem": "không nói rõ",
            "can_cu_phap_ly": [],
            "tom_tat": "",
            "luu_y": "",
        }

    def analyze_document(self, chunks, can_cu_text=""):
        """Analyze document chunks with optional legal basis (can_cu) from metadata."""
        print(f"[Analyze] Starting with {len(chunks)} chunks...")
        text_chunks = self._normalize_chunks(chunks)
        if not text_chunks:
            return self._empty_metadata()

        if len(text_chunks) > self.max_chunks:
            print(f"[Limit] Reducing {len(text_chunks)} chunks to first 20 and last 20...")
            text_chunks = text_chunks[:20] + text_chunks[-20:]

        extractions = []
        for idx, chunk_text in enumerate(text_chunks, 1):
            print(f"[Extract] Processing chunk {idx}/{len(text_chunks)}...")
            extractions.append(self._extract_chunk_info(chunk_text))

        print(f"[MergeTree] Building structured merge tree for {len(extractions)} extracted chunks...")
        merged = self._merge_tree(extractions)
        final_result = self._finalize_analysis(merged, can_cu_text=can_cu_text)
        return final_result

    def _normalize_chunks(self, chunks):
        text_chunks = []
        for chunk in chunks:
            if isinstance(chunk, dict):
                text = chunk.get("text", "")
            else:
                text = str(chunk)
            text = text.strip()
            if text:
                text_chunks.append(text)
        return text_chunks

    def _extract_json_object(self, text):
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if not match:
                return None
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                return None

    def _normalize_text_value(self, value):
        if isinstance(value, list):
            value = "; ".join(str(item).strip() for item in value if str(item).strip())
        value = str(value or "").strip()
        if not value:
            return "không nói rõ"
        # Strip markdown artifacts from LLM output
        value = re.sub(r"[*#>`_~]+", "", value).strip()
        return value if value else "không nói rõ"

    def _normalize_nhiem_vu(self, raw_list):
        """Normalize nhiem_vu list from LLM output."""
        if not isinstance(raw_list, list):
            return []
        valid_roles = {"chủ trì", "phối hợp", "thực hiện", "hỗ trợ", "chỉ đạo", "giám sát", "báo cáo"}
        tasks = []
        for item in raw_list:
            if not isinstance(item, dict):
                continue
            don_vi = str(item.get("don_vi", "")).strip()
            noi_dung = str(item.get("noi_dung", "")).strip()
            vai_tro = str(item.get("vai_tro", "")).strip().lower()
            if not don_vi or don_vi.lower() in ("không nói rõ", "không rõ", "?"):
                continue
            don_vi = re.sub(r"[*#>`_~]+", "", don_vi).strip()
            noi_dung = re.sub(r"[*#>`_~]+", "", noi_dung).strip()
            if vai_tro not in valid_roles:
                vai_tro = "thực hiện"
            tasks.append({
                "don_vi": don_vi,
                "noi_dung": noi_dung,
                "vai_tro": vai_tro,
            })
        return tasks

    def _normalize_extraction(self, data):
        normalized = self._empty_metadata()
        normalized["nhiem_vu"] = self._normalize_nhiem_vu(data.get("nhiem_vu", []))
        normalized["thoi_gian"] = self._normalize_text_value(data.get("thoi_gian", ""))
        normalized["kinh_phi"] = self._normalize_text_value(data.get("kinh_phi", ""))
        normalized["dia_diem"] = self._normalize_text_value(data.get("dia_diem", ""))
        normalized["tom_tat"] = str(data.get("tom_tat", "")).strip()
        normalized["luu_y"] = str(data.get("luu_y", "")).strip()
        normalized["_tom_tat_parts"] = [normalized["tom_tat"]] if normalized["tom_tat"] else []
        return normalized

    def _extract_by_rules(self, chunk):
        text = chunk or ""
        rule_data = {
            "nhiem_vu": [],
            "thoi_gian": "không nói rõ",
            "kinh_phi": "không nói rõ",
            "dia_diem": "không nói rõ",
        }

        # thoi_gian: gộp cả mốc bắt đầu, thời hạn, và mốc mô tả
        time_parts = []
        start_match = re.search(r"(?:từ ngày|bắt đầu từ ngày)\s*(\d{1,2}/\d{1,2}/\d{4})", text, re.IGNORECASE)
        if start_match:
            time_parts.append(f"từ {start_match.group(1).strip()}")

        deadline_items = self._extract_deadline_items(text)
        if deadline_items:
            time_parts.extend(deadline_items)

        # descriptive time: "thời gian thực hiện: cùng với...", "thời gian: hàng quý..."
        desc_time = re.search(
            r"[Tt]hời gian(?:\s+thực hiện)?[:]\s*([^\.\n]{5,200})",
            text,
        )
        if desc_time:
            val = desc_time.group(1).strip(" ,;")
            # avoid duplicating if it's just a date already captured
            if not re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", val):
                time_parts.append(val)

        if time_parts:
            rule_data["thoi_gian"] = "; ".join(time_parts)

        budget_match = re.search(r"(kinh phí[^\.;\n]*|nguồn chi[^\.;\n]*|ngân sách[^\.;\n]*)", text, re.IGNORECASE)
        if budget_match:
            rule_data["kinh_phi"] = budget_match.group(1).strip()

        location_match = re.search(r"(?:trên địa bàn|tại|trên phạm vi)\s+([^\.;\n]{3,140})", text, re.IGNORECASE)
        if location_match:
            rule_data["dia_diem"] = location_match.group(1).strip(" ,")

        # nhiem_vu: extract org + role pairs
        org_hint = re.compile(
            r"\b(BHXH|Bảo hiểm|UBND|Sở|Phòng|Bộ phận|Bộ|Cục|Ban|Tổ|Đội|Chi cục|"
            r"Trung tâm|Tổng cục|Hội đồng|Công an|Liên đoàn|Tòa|Viện|cơ quan)\b",
            re.IGNORECASE,
        )
        org_role_pattern = re.compile(
            r"([A-ZĐ][^\.;\n]{0,120}?)\s+"
            r"(chủ trì|phối hợp|thực hiện|chịu trách nhiệm|có trách nhiệm|hỗ trợ)",
            re.IGNORECASE
        )
        role_map = {
            "chủ trì": "chủ trì",
            "chịu trách nhiệm": "chủ trì",
            "có trách nhiệm": "thực hiện",
            "phối hợp": "phối hợp",
            "thực hiện": "thực hiện",
            "hỗ trợ": "hỗ trợ",
        }
        seen_orgs = set()
        for m in org_role_pattern.finditer(text):
            don_vi = m.group(1).strip(" ,")
            role_raw = m.group(2).strip().lower()
            if org_hint.search(don_vi) and don_vi.lower() not in seen_orgs:
                seen_orgs.add(don_vi.lower())
                rule_data["nhiem_vu"].append({
                    "don_vi": don_vi,
                    "noi_dung": "",
                    "vai_tro": role_map.get(role_raw, "thực hiện"),
                })

        giao_pattern = re.compile(
            r"(?:giao|giao cho)\s+([A-ZĐ][^\.;\n]{0,120}?)\s+(?:thực hiện|triển khai|tổ chức)",
            re.IGNORECASE
        )
        for m in giao_pattern.finditer(text):
            don_vi = m.group(1).strip(" ,")
            if org_hint.search(don_vi) and don_vi.lower() not in seen_orgs:
                seen_orgs.add(don_vi.lower())
                rule_data["nhiem_vu"].append({
                    "don_vi": don_vi,
                    "noi_dung": "",
                    "vai_tro": "thực hiện",
                })

        # Strip markdown from scalar values
        for key in ["thoi_gian", "kinh_phi", "dia_diem"]:
            if rule_data[key] != "không nói rõ":
                rule_data[key] = re.sub(r"[*#>`_~]+", "", rule_data[key]).strip()
                if not rule_data[key]:
                    rule_data[key] = "không nói rõ"

        return rule_data

    def _extract_deadline_items(self, text):
        patterns = [
            r"(?:báo\s*cáo[^\.;\n]{0,80}?trước\s+(?:ngày\s+)?\d{1,2}/\d{1,2}/\d{4})",
            r"(?:gửi[^\.;\n]{0,80}?trước\s+(?:ngày\s+)?\d{1,2}/\d{1,2}/\d{4})",
            r"(?:tổng\s*hợp[^\.;\n]{0,80}?trước\s+(?:ngày\s+)?\d{1,2}/\d{1,2}/\d{4})",
            r"(?:trong\s+thời\s+hạn\s+\d+\s*(?:ngày|tháng)[^\.;\n]*)",
            r"(?:sau\s+\d+\s*(?:ngày|tháng)[^\.;\n]*)",
            r"(?:\d+\s*(?:ngày|tháng)\s+kể\s+từ[^\.;\n]*)",
            r"(?:trước\s+(?:ngày\s+)?\d{1,2}/\d{1,2}/\d{4})",
            r"(?:(?:muộn\s+nhất|chậm\s+nhất)\s+là\s+ngày\s+\d{1,2}/\d{1,2}/\d{4})",
            r"(?:thời\s+điểm\s+\d{1,2}/\d{1,2}/\d{4})",
        ]

        hits = []
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                candidate = match.group(0).strip(" .,")
                if candidate:
                    hits.append((match.start(), candidate))

        hits.sort(key=lambda item: item[0])
        seen = []
        for _, candidate in hits:
            candidate = re.sub(r"\s+", " ", candidate).strip()
            if candidate and candidate not in seen:
                seen.append(candidate)
        return self._merge_deadline_items(seen)

    def _normalize_deadline_phrase(self, phrase):
        text = str(phrase or "").strip()
        text = re.sub(r"\btrước ngày\s+(\d{1,2}/\d{1,2}/\d{4})", r"trước \1", text, flags=re.IGNORECASE)
        text = re.sub(r"\btrong thời hạn\s+(\d+)\s+kể từ\b", r"trong thời hạn \1 ngày kể từ", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+", " ", text).strip(" .,")
        return text

    def _deadline_signature(self, phrase):
        normalized = self._normalize_deadline_phrase(phrase).lower()
        date_match = re.search(r"\d{1,2}/\d{1,2}/\d{4}", normalized)
        date_key = date_match.group(0) if date_match else ""

        duration_match = re.search(r"\b\d+\s*(?:ngày|tháng)\b", normalized)
        duration_key = duration_match.group(0) if duration_match else ""

        if re.search(r"\b(báo cáo|tổng hợp|gửi)\b", normalized):
            context_key = "report"
        elif re.search(r"\b(trong thời hạn|kể từ|sau)\b", normalized):
            context_key = "execution"
        else:
            context_key = "generic"

        return date_key, duration_key, context_key

    def _pick_better_deadline_phrase(self, left, right):
        left_n = self._normalize_deadline_phrase(left)
        right_n = self._normalize_deadline_phrase(right)

        left_report = re.search(r"\b(báo cáo|tổng hợp|gửi)\b", left_n, re.IGNORECASE) is not None
        right_report = re.search(r"\b(báo cáo|tổng hợp|gửi)\b", right_n, re.IGNORECASE) is not None

        if left_report and not right_report:
            return left_n
        if right_report and not left_report:
            return right_n

        if len(right_n) > len(left_n):
            return right_n
        return left_n

    def _merge_deadline_items(self, items):
        merged = []

        for item in items:
            candidate = self._normalize_deadline_phrase(item)
            if not candidate:
                continue

            cand_sig = self._deadline_signature(candidate)
            replaced = False

            for idx, existing in enumerate(merged):
                existing_sig = self._deadline_signature(existing)

                same_core = (
                    (cand_sig[0] and cand_sig[0] == existing_sig[0])
                    or (cand_sig[1] and cand_sig[1] == existing_sig[1])
                )

                contains_relation = candidate.lower() in existing.lower() or existing.lower() in candidate.lower()

                if same_core or contains_relation:
                    better = self._pick_better_deadline_phrase(existing, candidate)
                    merged[idx] = better
                    replaced = True
                    break

            if not replaced:
                merged.append(candidate)

        deduped = []
        for item in merged:
            if item not in deduped:
                deduped.append(item)

        return deduped

    def _sanitize_prompt_artifacts(self, text):
        raw = str(text or "").strip()
        if not raw:
            return raw

        cleaned_lines = []
        blocked_prefixes = (
            "ví dụ",
            "input:",
            "output:",
            "kết quả tốt",
            "kết quả:",
            "các ý đầu vào",
            "các ý cần gộp",
        )
        for line in raw.splitlines():
            stripped = line.strip()
            lowered = stripped.lower()
            if not stripped:
                continue
            if lowered.startswith(blocked_prefixes):
                continue
            if stripped.startswith("→"):
                stripped = stripped.lstrip("→").strip()
            cleaned_lines.append(stripped)

        cleaned = " ".join(cleaned_lines)
        cleaned = re.sub(r"\b(Kết quả tốt|Kết quả|Ví dụ|Input|Output)\s*:\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\[[A-Z_]+\]", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def _build_structured_summary(self, result):
        sentences = []
        tasks = result.get("nhiem_vu", [])
        if tasks:
            chu_tri = [t for t in tasks if t.get("vai_tro") == "chủ trì"]
            for t in chu_tri:
                s = f"{t['don_vi']} chủ trì"
                if t.get("noi_dung"):
                    s += f" {t['noi_dung']}"
                sentences.append(s)
            phoi_hop = [t for t in tasks if t.get("vai_tro") == "phối hợp"]
            if phoi_hop:
                names = ", ".join(t["don_vi"] for t in phoi_hop)
                sentences.append(f"Phối hợp: {names}")
            thuc_hien = [t for t in tasks if t.get("vai_tro") not in ("chủ trì", "phối hợp")]
            for t in thuc_hien:
                s = t["don_vi"]
                if t.get("noi_dung"):
                    s += f": {t['noi_dung']}"
                sentences.append(s)

        if result.get("thoi_gian") != "không nói rõ":
            sentences.append(f"Thời gian: {result['thoi_gian']}")
        if result.get("kinh_phi") != "không nói rõ":
            sentences.append(f"Kinh phí: {result['kinh_phi']}")
        if result.get("dia_diem") != "không nói rõ":
            sentences.append(f"Địa điểm: {result['dia_diem']}")
        if result.get("can_cu_phap_ly"):
            sentences.append(f"Căn cứ pháp lý: {', '.join(result['can_cu_phap_ly'])}")

        return ". ".join(sentences) + "." if sentences else ""

    def _validate_chunk_extraction(self, normalized, chunk, rule_data):
        """Validate and fill extraction from rules where LLM missed."""
        # thoi_gian
        if normalized.get("thoi_gian") == "không nói rõ" and rule_data.get("thoi_gian") != "không nói rõ":
            normalized["thoi_gian"] = rule_data["thoi_gian"]
        # kinh_phi
        if normalized.get("kinh_phi") == "không nói rõ" and rule_data.get("kinh_phi") != "không nói rõ":
            normalized["kinh_phi"] = rule_data["kinh_phi"]
        # dia_diem
        if normalized.get("dia_diem") == "không nói rõ" and rule_data.get("dia_diem") != "không nói rõ":
            normalized["dia_diem"] = rule_data["dia_diem"]
        # nhiem_vu: add rule-based tasks if LLM returned empty
        if not normalized.get("nhiem_vu") and rule_data.get("nhiem_vu"):
            normalized["nhiem_vu"] = rule_data["nhiem_vu"]

        # Sanitize free-form fields
        normalized["tom_tat"] = self._sanitize_prompt_artifacts(normalized.get("tom_tat", ""))
        normalized["luu_y"] = self._sanitize_prompt_artifacts(normalized.get("luu_y", ""))

        return normalized

    def _fill_missing_fields_with_rules(self, normalized, chunk):
        rule_data = self._extract_by_rules(chunk)
        return self._validate_chunk_extraction(normalized, chunk, rule_data)

    def _contains_english(self, text):
        if not text:
            return False
        return re.search(r"\b(the|and|this|that|is|are|activity|funded|from|for|with|summary)\b", text, re.IGNORECASE) is not None


    def _build_extraction_prompt(self, chunk):
        return f"""Bạn là hệ thống trích xuất thông tin từ văn bản pháp luật, hành chính tiếng Việt.

NHIỆM VỤ:
- Đọc KỸ toàn bộ nội dung trong thẻ <VAN_BAN>.
- Trích xuất thông tin theo đúng schema bên dưới.
- Chỉ lấy thông tin thực sự có trong đoạn văn bản.
- Không suy diễn, không bịa thêm, không dịch sang tiếng Anh.
- Nếu không có thông tin cho một trường, ghi đúng: "không nói rõ".
- Trả về duy nhất một JSON object hợp lệ, không giải thích gì thêm.

QUAN TRỌNG:
- Khối <VI_DU> chỉ minh họa cách trả lời, KHÔNG phải dữ liệu cần phân tích.
- Tuyệt đối không chép tên riêng, số liệu, cơ quan từ <VI_DU> vào kết quả.

SCHEMA:
{{
  "nhiem_vu": [
    {{
      "don_vi": "tên đầy đủ của đơn vị/tổ chức",
      "noi_dung": "nhiệm vụ cụ thể, bao gồm cả biện pháp và cách thức triển khai",
      "vai_tro": "chủ trì | phối hợp | thực hiện | hỗ trợ | giám sát | báo cáo"
    }}
  ],
  "thoi_gian": "mỗi mốc thời gian KÈM ngữ cảnh (liên quan đến nhiệm vụ/bước nào). Ví dụ: '10 ngày đối với kiểm tra chuyên ngành; trước 20/12 hàng năm đối với báo cáo tổng hợp'",
  "kinh_phi": "nguồn hoặc mức kinh phí, ngân sách nếu có",
  "dia_diem": "chỉ địa bàn thực tế (tỉnh, huyện, quận, đơn vị). KHÔNG ghi tham chiếu văn bản (nư 'điểm 1', 'tiết a2', 'phần mềm TST')",
  "tom_tat": "tóm tắt 2-3 câu bằng tiếng Việt: ai làm gì, bằng cách nào, ở đâu, khi nào",
  "luu_y": "điểm đáng chú ý, yêu cầu đặc biệt, điều kiện ràng buộc nếu có"
}}

CÁCH PHÂN TÍCH (đọc kỹ trước khi trả lời):

Bước 1 - Tìm CHỦ THỂ (ai?):
  Tìm tất cả đơn vị/tổ chức/bộ phận được nhắc đến.
  Mỗi đơn vị → 1 object trong mảng "nhiem_vu".

Bước 2 - Tìm NỘI DUNG CÔNG VIỆC, tập trung vào BIỆN PHÁP THỰC HIỆN (làm gì? bằng cách nào?):
  Với mỗi đơn vị, xác định:
  - Nhiệm vụ chính được giao (ví dụ: xây dựng kế hoạch, rà soát dữ liệu, phân bổ ngân sách, chỉ tiêu,
  đôn đốc, kiểm tra)
  - BIỆN PHÁP triển khai cụ thể, ưu tiên các hành động như:
    + lập kế hoạch, xây dựng kịch bản
    + rà soát, phân loại, đối chiếu dữ liệu
    + phân bổ, giao chỉ tiêu (ghi rõ số lượng nếu văn bản nêu)
    + kiểm tra, đôn đốc, đánh giá việc thực hiện
    + tổ chức hội nghị, làm việc trực tiếp
    + cập nhật, nâng cấp phần mềm, hệ thống
    + tổng hợp báo cáo
  - Căn cứ/cơ sở thực hiện (ví dụ: căn cứ danh sách trên phần mềm, theo Mẫu số X)
  - Sản phẩm đầu ra nếu có (ví dụ: lập danh sách, gửi báo cáo)
  Ghi TẤT CẢ vào trường "noi_dung", KHÔNG cắt ngắn, giữ đủ ý nghĩa.
  Nếu có số liệu cụ thể (số đơn vị, số chỉ tiêu, tỷ lệ...) thì GHI KÈM vào noi_dung.

Bước 3 - Tìm VAI TRÒ (chủ thể đóng vai gì?):
  Dựa vào tín hiệu ngôn ngữ trong đoạn:
  + "chủ trì" / "chịu trách nhiệm" → vai_tro = "chủ trì"
  + "phối hợp" / "phối hợp với" → vai_tro = "phối hợp"
  + được giao nhiệm vụ cụ thể → vai_tro = "thực hiện"
  + "đảm bảo" / "hỗ trợ" / "cung cấp" → vai_tro = "hỗ trợ"
  + "kiểm tra" / "đôn đốc" / "theo dõi" → vai_tro = "giám sát"
  + "báo cáo" / "tổng hợp" → vai_tro = "báo cáo"
  

Bước 4 - Tìm THỜI GIAN (khi nào?) và GHI KÈM NGỮ CẢNH:
  Tìm MỌI mốc thời gian xuất hiện trong đoạn:
  - Ngày/tháng/năm cụ thể: "ngày 01/04/2026", "trước ngày 30/6/2026"
  - Mốc tương đối: "trong thời hạn 15 ngày", "hàng tháng", "hàng quý"
  - Mốc gắn sự kiện: "cùng thời điểm lập dự toán", "khi được phê duyệt"
  Với MỖI mốc, ghi thêm nó liên quan đến nhiệm vụ/bước nào.
  Ví dụ: "trong thời hạn 10 ngày đối với kiểm tra chuyên ngành; cùng thời điểm lập dự toán đối với xây dựng kế hoạch"
  Ngăn cách bằng dấu chấm phẩy.

Bước 5 - Tìm KINH PHÍ, ĐỊA ĐIỂM, LƯU Ý:
  - Địa điểm: CHỈ ghi địa bàn thực tế (tên tỉnh, quận, huyện, đơn vị), 
    KHÔNG ghi tham chiếu văn bản như "điểm 1", "tiết a2", "phần mềm TST".
  - Lưu ý: chỉ ghi nếu có điều kiện ràng buộc/yêu cầu đặc biệt thực sự.
    Nếu không có gì đặc biệt → "không có". KHÔNG ghi "không nói rõ".

Bước 6 - Viết TÓM TẮT 2-3 câu, FOCUS vào BIỆN PHÁP THỰC HIỆN:
  Nêu rõ: chủ thể chính triển khai bằng biện pháp gì (lập kế hoạch, rà soát, phân bổ chỉ tiêu,
  kiểm tra...), ở đâu, khi nào. Nếu có số liệu cụ thể thì đưa vào.
  Nếu quá nhiều nội dung → chọn 2-3 biện pháp quan trọng nhất.

<VI_DU>
Input mẫu:
"Từ ngày 01/04/2026, Ban Quản lý thu chủ trì triển khai rà soát doanh nghiệp tại quận Ba Đình.
Thời gian thực hiện: cùng với thời điểm lập dự toán thu chi hàng năm.
Phòng Kiểm tra phối hợp xác minh thông tin. Kinh phí từ nguồn chi quản lý BHXH.
Báo cáo kết quả trước ngày 30/06/2026."

Output mẫu:
{{
  "nhiem_vu": [
    {{"don_vi": "Ban Quản lý thu", "noi_dung": "chủ trì triển khai rà soát doanh nghiệp, căn cứ dữ liệu trên phần mềm để xác minh tình trạng tham gia", "vai_tro": "chủ trì"}},
    {{"don_vi": "Phòng Kiểm tra", "noi_dung": "phối hợp xác minh thông tin doanh nghiệp", "vai_tro": "phối hợp"}}
  ],
  "thoi_gian": "từ 01/04/2026 đối với rà soát doanh nghiệp; cùng thời điểm lập dự toán thu chi hàng năm đối với kế hoạch; báo cáo trước 30/06/2026",
  "kinh_phi": "nguồn chi quản lý BHXH",
  "dia_diem": "quận Ba Đình",
  "tom_tat": "Ban Quản lý thu chủ trì rà soát doanh nghiệp tại Ba Đình từ 01/04/2026. Phòng Kiểm tra phối hợp xác minh. Thời gian thực hiện gắn với thời điểm lập dự toán, báo cáo trước 30/06/2026.",
  "luu_y": "không có"
}}
</VI_DU>

<VAN_BAN>
{chunk}
</VAN_BAN>

JSON:"""

    def _extract_chunk_info(self, chunk):
        prompt = self._build_extraction_prompt(chunk)
        response = self.generate(prompt)
        data = self._extract_json_object(response)
        if data is None:
            # Fallback: rule-based extraction only
            normalized = self._empty_metadata()
            normalized["tom_tat"] = chunk[:300]
            normalized = self._fill_missing_fields_with_rules(normalized, chunk)
            return normalized

        normalized = self._normalize_extraction(data)
        normalized = self._fill_missing_fields_with_rules(normalized, chunk)
        return normalized

    def _merge_unique_text(self, left_value, right_value, joiner="; "):
        """Merge two text values as UNION: split segments, dedup, remove substrings."""
        segments = []
        for value in [left_value, right_value]:
            value = str(value or "").strip()
            if not value or value in ("không nói rõ", "không có"):
                continue
            for seg in re.split(r";\s*", value):
                seg = seg.strip(" ,.")
                if seg and seg not in ("không nói rõ", "không có"):
                    segments.append(seg)
        # Dedup: exact + substring elimination
        unique = []
        for seg in segments:
            seg_lower = seg.lower().strip()
            # Skip if substring of something already collected
            if any(seg_lower in existing.lower() for existing in unique):
                continue
            # Remove existing items that are substrings of this new one
            unique = [u for u in unique if u.lower().strip() not in seg_lower]
            unique.append(seg)
        return joiner.join(unique) if unique else "không nói rõ"

    def _merge_luu_y(self, left_value, right_value):
        """Merge luu_y with proper filtering and dedup."""
        skip = {"không nói rõ", "không có", "không", ""}
        segments = []
        for value in [left_value, right_value]:
            value = str(value or "").strip()
            if value.lower() in skip:
                continue
            for seg in re.split(r";\s*", value):
                seg = seg.strip(" ,.")
                if seg and seg.lower() not in skip:
                    segments.append(seg)
        # Dedup
        unique = []
        for seg in segments:
            if not any(seg.lower() in u.lower() or u.lower() in seg.lower() for u in unique):
                unique.append(seg)
        return "; ".join(unique) if unique else ""

    def _clean_dia_diem(self, value):
        """Filter out non-geographic noise from dia_diem after merge."""
        if not value or value == "không nói rõ":
            return value
        junk = re.compile(
            r"^(điểm \d|tiết [a-z]|khoản \d|mục \d|phần mềm|đường dẫn|"
            r"mẫu số|báo cáo tình|hội nghị đảm bảo|từ báo cáo)",
            re.IGNORECASE,
        )
        segments = [s.strip() for s in re.split(r"[;,]\s*", value)]
        clean = [s for s in segments if s and not junk.search(s)]
        return "; ".join(clean) if clean else "không nói rõ"

    def _merge_text_parts(self, left_parts, right_parts):
        merged = []
        for part in list(left_parts or []) + list(right_parts or []):
            part = str(part).strip()
            if part and part not in merged:
                merged.append(part)
        return merged

    def _merge_nhiem_vu(self, left_tasks, right_tasks):
        """Merge two nhiem_vu lists as UNION: org-level dedup, sentence-level noi_dung dedup."""
        merged = []
        seen = set()
        for task in list(left_tasks or []) + list(right_tasks or []):
            key = task.get("don_vi", "").strip().lower()
            if not key or key in ("không nói rõ", "không rõ", "?"):
                continue
            # Check for substring-level dup
            is_dup = any(
                key in existing or existing in key
                for existing in seen
            )
            if not is_dup:
                seen.add(key)
                merged.append(dict(task))  # copy to avoid mutation
            else:
                # If same org, merge noi_dung at sentence level (union, not concat)
                for existing_task in merged:
                    ek = existing_task["don_vi"].strip().lower()
                    if key in ek or ek in key:
                        existing_nd = existing_task.get("noi_dung", "")
                        new_nd = task.get("noi_dung", "")
                        existing_task["noi_dung"] = self._merge_noi_dung(existing_nd, new_nd)
                        break
        return merged

    def _merge_noi_dung(self, existing, new):
        """Merge noi_dung strings as union at sentence/clause level."""
        if not new:
            return existing
        if not existing:
            return new
        # Split existing into clauses for dedup
        existing_clauses = set()
        for clause in re.split(r';\s*', existing):
            c = clause.strip().lower()
            if c:
                existing_clauses.add(c)
        # Only add genuinely new clauses from right side
        fresh = []
        for clause in re.split(r';\s*', new):
            c = clause.strip()
            c_lower = c.lower()
            if not c:
                continue
            # Skip if exact match or substring of existing
            if c_lower in existing_clauses:
                continue
            if any(c_lower in ec for ec in existing_clauses):
                continue
            # Skip if existing clause is substring of this (keep the longer one already there)
            if any(ec in c_lower for ec in existing_clauses):
                # This new clause is more detailed — replace the shorter one
                # For simplicity, just add it (won't duplicate much)
                pass
            fresh.append(c)
        if fresh:
            return f"{existing}; {'; '.join(fresh)}"
        return existing

    def _merge_two_structured(self, left, right):
        merged = self._empty_metadata()
        merged["nhiem_vu"] = self._merge_nhiem_vu(left.get("nhiem_vu", []), right.get("nhiem_vu", []))
        merged["thoi_gian"] = self._merge_unique_text(left.get("thoi_gian"), right.get("thoi_gian"))
        merged["kinh_phi"] = self._merge_unique_text(left.get("kinh_phi"), right.get("kinh_phi"), joiner=", ")
        merged["dia_diem"] = self._merge_unique_text(left.get("dia_diem"), right.get("dia_diem"), joiner=", ")
        merged["_tom_tat_parts"] = self._merge_text_parts(left.get("_tom_tat_parts", []), right.get("_tom_tat_parts", []))
        merged["tom_tat"] = " ".join(merged["_tom_tat_parts"])
        merged["luu_y"] = self._merge_luu_y(left.get("luu_y", ""), right.get("luu_y", ""))
        return merged

    def _merge_tree(self, items):
        if not items:
            return self._empty_metadata()

        current_level = items[:]
        level = 1
        while len(current_level) > 1:
            print(f"[MergeTree] Level {level}: reducing {len(current_level)} items...")
            next_level = []
            for index in range(0, len(current_level), 2):
                left = current_level[index]
                if index + 1 >= len(current_level):
                    next_level.append(left)
                    continue
                right = current_level[index + 1]
                next_level.append(self._merge_two_structured(left, right))
            current_level = next_level
            level += 1
        return current_level[0]

    def _build_summary_prompt(self, merged):
        tasks_text = ""
        for t in merged.get("nhiem_vu", []):
            tasks_text += f"- {t['don_vi']} ({t['vai_tro']}): {t.get('noi_dung', '')}\n"
        if not tasks_text:
            tasks_text = "không nói rõ"

        return f"""Bạn là trợ lý pháp lý Việt Nam.

Hãy viết tóm tắt tổng hợp bằng tiếng Việt dựa trên thông tin bên dưới.

YÊU CẦU:
- Chỉ dùng tiếng Việt, không markdown, không tiêu đề tiếng Anh.
- Dài 4-6 câu, mạch lạc, không lặp ý.
- FOCUS vào BIỆN PHÁP THỰC HIỆN: lập kế hoạch, rà soát dữ liệu, phân bổ chỉ tiêu,
kiểm tra, tổ chức hội nghị, v.v. theo một mạch logic thống nhất
- Nêu rõ: ai với vai trò chủ trì/phối hợp, triển khai bằng biện pháp gì, thời gian, địa điểm,
dùng mẫu biểu nào ở đâu (mẫu biểu ở phục lục hay trong mục, điểm, hoặc văn bản nào cần chỉ rõ)
- Nếu có số liệu cụ thể (số đơn vị, chỉ tiêu, tỷ lệ...) thì đưa vào tóm tắt.
- Không thêm thông tin ngoài dữ liệu đã cho.

DỮ LIỆU:
Nhiệm vụ các đơn vị:
{tasks_text}
Thời gian: {merged.get('thoi_gian', 'không nói rõ')}
Kinh phí: {merged.get('kinh_phi', 'không nói rõ')}
Địa điểm: {merged.get('dia_diem', 'không nói rõ')}
Căn cứ pháp lý: {', '.join(merged.get('can_cu_phap_ly', [])) or 'không nói rõ'}
Lưu ý: {merged.get('luu_y', 'không có')}

Tóm tắt:"""

    def _build_synthesis_prompt(self, nhiem_vu_list):
        """Build prompt to synthesize nhiem_vu into logical implementation workflow."""
        tasks_text = ""
        for i, t in enumerate(nhiem_vu_list, 1):
            don_vi = t.get("don_vi", "?")
            vai_tro = t.get("vai_tro", "")
            noi_dung = t.get("noi_dung", "")
            tasks_text += f"{i}. [{vai_tro}] {don_vi}: {noi_dung}\n"

        return f"""Bạn là chuyên gia phân tích văn bản hành chính Việt Nam.

NHIỆM VỤ:
Dựa trên danh sách nhiệm vụ các đơn vị bên dưới, hãy tổng hợp thành QUY TRÌNH THỰC HIỆN
theo trình tự logic từ đầu đến cuối.

QUY TẮC:
1. Sắp xếp các bước theo trình tự logic: chuẩn bị → lập kế hoạch → triển khai → kiểm tra → báo cáo.
2. Mỗi bước nêu rõ: hành động gì, ai thực hiện, dùng công cụ/mẫu biểu gì (nếu có).
3. Kết nối các nhiệm vụ liên quan từ nhiều đơn vị thành một mạch thống nhất.
   Ví dụ: rà soát dữ liệu (đơn vị A) → lập danh sách (đơn vị A) → gửi thông báo (đơn vị B) → kiểm tra (đơn vị C).
4. Số bước: 5-10 bước, mỗi bước 1-2 câu ngắn gọn.
5. Chỉ dùng tiếng Việt. Không markdown. Không tiêu đề tiếng Anh.
6. Không bịa thêm, chỉ dùng thông tin có trong dữ liệu.
7. Trả về duy nhất 1 JSON array hợp lệ, KHÔNG giải thích gì thêm.

ĐỊNH DẠNG:
[
  {{"buoc": 1, "hanh_dong": "mô tả hành động", "don_vi": "ai thực hiện"}},
  {{"buoc": 2, "hanh_dong": "mô tả hành động", "don_vi": "ai thực hiện"}}
]

DỮ LIỆU NHIỆM VỤ:
{tasks_text}

JSON:"""

    def _synthesize_workflow(self, nhiem_vu_list):
        """Use LLM to synthesize nhiem_vu into a logical implementation workflow."""
        if not nhiem_vu_list or len(nhiem_vu_list) < 2:
            return []

        prompt = self._build_synthesis_prompt(nhiem_vu_list)
        try:
            raw = self.generate(prompt)
            data = self._extract_json_array(raw)
            if not data:
                return []
            # Validate and clean
            steps = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                buoc = item.get("buoc", len(steps) + 1)
                hanh_dong = str(item.get("hanh_dong", "")).strip()
                don_vi = str(item.get("don_vi", "")).strip()
                if hanh_dong:
                    hanh_dong = re.sub(r"[*#>`_~]+", "", hanh_dong).strip()
                    don_vi = re.sub(r"[*#>`_~]+", "", don_vi).strip()
                    steps.append({
                        "buoc": int(buoc) if isinstance(buoc, (int, float)) else len(steps) + 1,
                        "hanh_dong": hanh_dong,
                        "don_vi": don_vi,
                    })
            return steps[:12]  # Max 12 steps
        except Exception as e:
            print(f"[Synthesis] Error: {e}")
            return []

    def _extract_json_array(self, text):
        """Extract a JSON array from LLM response."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            result = json.loads(cleaned)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass
        match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group())
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                pass
        return None

    def _parse_can_cu_into_issues(self, can_cu_text):
        """Parse 'Căn cứ' (legal basis) text into structured list of legal basis items."""
        if not can_cu_text or not can_cu_text.strip():
            return []
        
        # Remove 'Căn cứ' prefix if present
        text = re.sub(r"^\s*Căn\s+cứ\s+", "", can_cu_text.strip(), flags=re.IGNORECASE)
        
        # Split by common separators and numbered items
        # Handle patterns like: "1.", "a)", "-", ";"
        issues = []
        
        # First try to split by numbered/lettered items
        items = re.split(r"(?:^|\n)\s*(?:\d+\.|[a-z]\)|[-•])", text)
        items = [item.strip(" ;,") for item in items if item.strip()]
        
        if items:
            # Filter out very short items (likely noise)
            issues = [item for item in items if len(item) > 5]
        
        # If no structured items found, split by semicolon or newline
        if not issues:
            items = re.split(r"[;\n]", text)
            issues = [item.strip(" ,-") for item in items if item.strip() and len(item) > 5]
        
        return issues[:10]  # Limit to 10 items

    def _log_unknown_fields(self, result):
        unknown_fields = []
        for field in ["thoi_gian", "kinh_phi", "dia_diem"]:
            if result.get(field) == "không nói rõ":
                unknown_fields.append(field)
        if not result.get("nhiem_vu"):
            unknown_fields.append("nhiem_vu")
        if unknown_fields:
            print(f"[Feedback] Không đủ căn cứ rõ ràng cho: {', '.join(unknown_fields)}")

    def _finalize_analysis(self, merged, can_cu_text=""):
        result = self._empty_metadata()

        # nhiem_vu: dedup and clean
        result["nhiem_vu"] = merged.get("nhiem_vu", [])
        result["thoi_gian"] = merged.get("thoi_gian", "không nói rõ")
        result["kinh_phi"] = merged.get("kinh_phi", "không nói rõ")
        result["dia_diem"] = self._clean_dia_diem(merged.get("dia_diem", "không nói rõ"))
        result["luu_y"] = self._sanitize_prompt_artifacts(merged.get("luu_y", ""))

        # can_cu_phap_ly from metadata (not from chunks)
        result["can_cu_phap_ly"] = self._parse_can_cu_into_issues(can_cu_text) if can_cu_text else []
        if result["can_cu_phap_ly"]:
            print(f"[Legal Basis] Extracted {len(result['can_cu_phap_ly'])} items from căn cứ")

        # quy_trinh: synthesize nhiem_vu into logical workflow steps
        if result["nhiem_vu"]:
            print(f"[Synthesis] Building workflow from {len(result['nhiem_vu'])} tasks...")
            result["quy_trinh"] = self._synthesize_workflow(result["nhiem_vu"])
            print(f"[Synthesis] Generated {len(result['quy_trinh'])} workflow steps")

        # tom_tat: v1 = structured, v2 = LLM refined
        v1_summary = self._build_structured_summary(result)
        try:
            v2_prompt = self._build_summary_prompt(result)
            v2_raw = self.generate(v2_prompt)
            v2_clean = self._sanitize_prompt_artifacts(v2_raw)
            if v2_clean and not self._contains_english(v2_clean):
                result["tom_tat"] = v2_clean
            else:
                result["tom_tat"] = v1_summary
        except Exception:
            result["tom_tat"] = v1_summary

        self._log_unknown_fields(result)
        return result