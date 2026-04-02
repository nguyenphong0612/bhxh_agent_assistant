import re
from typing import Dict, List, Tuple


class TextSplitter:
	"""
	Unified splitter: auto-chooses strategy by priority.
	
	Priority chain (top-down, first match wins):
	  1. Markdown headings (#, ##, ###) — from pypandoc output
	  2. Text patterns (Phần/Chương, Điều, I., 1., a)...) — for plain text
	  3. No match → return text as single chunk
	
	Supports recursive splitting:
	  split(body_text) → 3 sections at # level
	  split(section)   → sub-sections at ## level (or text patterns)
	"""

	def __init__(self, chunk_size: int = 500, overlap: int = 50, min_length: int = 80):
		self.chunk_size = chunk_size
		self.overlap = overlap
		self.min_length = min_length

		# Text-based patterns (for plain text or fallback)
		self.patterns: List[Tuple[str, re.Pattern]] = [
			("chapter", re.compile(r"(?m)^\s*(?:Phần|Chương)\s+(?:[IVXLC]+|\d+)\b", re.IGNORECASE)),
			("article", re.compile(r"(?m)^\s*Điều\s+\d+\b", re.IGNORECASE)),
			("roman", re.compile(r"(?m)^\s*[IVXLC]{1,8}(?:\s*[\.\)\-:]\s+|\s+[A-ZÀ-ỸĐ])", re.IGNORECASE)),
			("upper_alpha", re.compile(r"(?m)^\s*[A-Z][\.\)\-:]\s*")),
			("sub_number", re.compile(r"(?m)^\s*\d+\.\d+\b", re.IGNORECASE)),
			("khoan", re.compile(r"(?m)^\s*\d+\.\s+")),
			("diem", re.compile(r"(?m)^\s*[a-z]\d*[\)\.]\s*")),
		]

	# ═══════════════════════════════════════════
	# PUBLIC: single entry point
	# ═══════════════════════════════════════════

	def split(self, text: str) -> List[Dict]:
		"""
		Split text by first matching strategy:
		  1. Try markdown headings
		  2. Try text patterns
		  3. Return as single chunk
		"""
		content = (text or "").strip()
		if not content:
			return []

		# Strategy 1: markdown headings
		result = self._split_by_headings(content)
		if result:
			return result

		# Strategy 2: text patterns
		result = self._split_by_patterns(content)
		if result:
			return result

		# Strategy 3: no split possible
		return [{
			"text": content,
			"metadata": {
				"split_by": "none",
				"level": 0,
				"chunk_index": 0,
				"header": self._extract_header(content),
			},
		}]

	# ═══════════════════════════════════════════
	# PUBLIC: recursive split with size control
	# ═══════════════════════════════════════════

	def split_recursive(self, text: str, max_chunk_size: int = 4000, _depth: int = 0, _max_depth: int = 5) -> List[Dict]:
		"""
		Recursively split text until all chunks are under max_chunk_size.

		Any chunk exceeding the threshold is re-split using split().
		Works generically for any document structure — no hardcoded section indices.
		Post-processes to merge weak/broken chunks with neighbors.

		Args:
			max_chunk_size: Maximum chars per chunk before triggering re-split.
			_depth/_max_depth: Internal recursion guard.
		"""
		chunks = self.split(text)
		if _depth >= _max_depth:
			return self._post_process(chunks, max_chunk_size)

		final: List[Dict] = []
		for chunk in chunks:
			if len(chunk["text"]) > max_chunk_size:
				sub_chunks = self.split_recursive(
					chunk["text"],
					max_chunk_size=max_chunk_size,
					_depth=_depth + 1,
					_max_depth=_max_depth,
				)
				# Only use sub-chunks if split actually produced >1 piece
				if len(sub_chunks) > 1:
					final.extend(sub_chunks)
				else:
					final.append(chunk)
			else:
				final.append(chunk)

		# Post-process: merge weak chunks, fix broken tails
		final = self._post_process(final, max_chunk_size)

		# Re-index chunk_index sequentially
		for idx, chunk in enumerate(final):
			chunk["metadata"]["chunk_index"] = idx
		return final

	# ═══════════════════════════════════════════
	# STRATEGY 1: Markdown headings
	# ═══════════════════════════════════════════

	def _split_by_headings(self, text: str) -> List[Dict]:
		"""
		Split by markdown heading markers (#, ##, ###).
		Auto-detects split level: skips first heading, picks shallowest among rest.
		Returns [] if fewer than 2 headings found.
		"""
		heading_re = re.compile(r'^(#{1,6})\s*(.*)')
		lines = text.splitlines(keepends=True)

		# Scan all non-empty headings
		all_headings = []
		for line in lines:
			m = heading_re.match(line)
			if m and m.group(2).strip():
				all_headings.append(len(m.group(1)))

		if len(all_headings) < 2:
			return []

		# Skip first heading (section title), split at shallowest among rest
		split_level = min(all_headings[1:])

		sections: List[Dict] = []
		current_heading = ""
		current_level = 0
		current_lines: List[str] = []
		preamble_lines: List[str] = []
		found_first = False
		chunk_idx = 0

		for line in lines:
			m = heading_re.match(line)
			if m:
				hlevel = len(m.group(1))
				htext = m.group(2).strip()
				if hlevel == split_level and htext:
					# Flush preamble
					if not found_first and preamble_lines:
						preamble_text = "".join(preamble_lines).strip()
						if len(preamble_text) >= self.min_length:
							sections.append({
								"text": preamble_text,
								"metadata": {
									"split_by": "heading_md",
									"level": split_level,
									"chunk_index": chunk_idx,
									"header": self._extract_header(preamble_text),
								},
							})
							chunk_idx += 1
					# Flush previous section
					if found_first and current_lines:
						section_text = "".join(current_lines).strip()
						if len(section_text) >= self.min_length:
							sections.append({
								"text": section_text,
								"metadata": {
									"split_by": "heading_md",
									"level": current_level,
									"chunk_index": chunk_idx,
									"header": current_heading,
								},
							})
							chunk_idx += 1
					found_first = True
					current_heading = htext
					current_level = hlevel
					current_lines = [line]
					continue
			if found_first:
				current_lines.append(line)
			else:
				preamble_lines.append(line)

		# Flush last section
		if found_first and current_lines:
			section_text = "".join(current_lines).strip()
			if len(section_text) >= self.min_length:
				sections.append({
					"text": section_text,
					"metadata": {
						"split_by": "heading_md",
						"level": current_level,
						"chunk_index": chunk_idx,
						"header": current_heading,
					},
				})

		return sections

	# ═══════════════════════════════════════════
	# STRATEGY 2: Text patterns
	# ═══════════════════════════════════════════

	def _split_by_patterns(self, text: str) -> List[Dict]:
		"""
		Split by first matching text pattern (priority order).
		Returns [] if no pattern produces >1 part.
		"""
		for name, pattern in self.patterns:
			parts = self._split_by_positions(text, pattern)
			if len(parts) > 1:
				results: List[Dict] = []
				for idx, part in enumerate(parts):
					normalized = part.strip()
					if not normalized:
						continue
					results.append({
						"text": normalized,
						"metadata": {
							"split_by": name,
							"level": 0,
							"chunk_index": idx,
							"header": self._extract_header(normalized),
						},
					})
				return results
		return []

	# ═══════════════════════════════════════════
	# POST-PROCESSING: merge weak/broken chunks
	# ═══════════════════════════════════════════

	def _is_weak_chunk(self, text: str) -> bool:
		"""Detect broken, dropped-word, meaningless, or too-short chunks."""
		if not text or not text.strip():
			return True
		t = text.strip()
		if len(t) < 24:
			return True
		# Starts with a continuation token → was split mid-sentence
		if re.match(r"^(và |hoặc |, |; |\. |: |\))", t):
			return True
		# Lowercase-leading without structural marker → likely a broken fragment
		if re.match(r"^[a-zà-ỹđ]", t) and not re.match(r"^[a-z]\d*[\)\.]\s+", t):
			return True
		# Markdown decorative residue (empty headings, blockquote-only)
		stripped_md = re.sub(r"^[>#*\s]+", "", t)
		if len(stripped_md) < 10:
			return True
		return False

	def _ends_with_connector(self, text: str) -> bool:
		"""Chunk ends mid-reference (e.g. 'Mẫu số:', 'Phụ lục:')."""
		return bool(
			re.search(r"\b(mẫu số|phụ lục|biểu số)\s*:\s*$", text, re.IGNORECASE)
			or text.rstrip().endswith((":", "(", "-", "/"))
		)

	def _looks_like_section_start(self, text: str) -> bool:
		"""Text opens with a structural marker — should stay standalone."""
		t = text.strip()
		# Markdown heading
		if re.match(r"^#{1,6}\s+\S", t):
			return True
		return bool(
			re.match(r"^(?:Phần|Chương)\s+(?:[IVXLC]+|\d+)\b", t, re.IGNORECASE)
			or re.match(r"^Điều\s+\d+\b", t, re.IGNORECASE)
			or re.match(r"^[IVXLC]+[\.\)]\s+", t)
			or re.match(r"^\d+\.\d+\b", t)
			or re.match(r"^\d+\.\s+", t)
			or re.match(r"^[a-z]\d*[\)\.]\s+", t)
			or re.match(r"^[A-Z][\.\)\-:]\s+", t)
		)

	def _take_until_nearest_period(self, text: str) -> Tuple[str, str]:
		"""Split at first period — take the completed sentence, leave the rest."""
		s = text.strip()
		if not s:
			return "", ""
		m = re.search(r"\.", s)
		if not m:
			return s, ""
		cut = m.end()
		return s[:cut].strip(), s[cut:].strip()

	def _post_process(self, chunks: List[Dict], max_chunk_size: int) -> List[Dict]:
		"""
		Merge weak/broken chunks with neighbors (from splitter_legacy logic).
		Rules:
		  1. If prev chunk ends with connector → attach start of current chunk
		  2. If current chunk is a section start AND substantial → keep standalone
		  3. If current chunk is a short section start → prepend to next chunk
		  4. If current chunk is weak → merge into previous (if size allows)
		  5. Otherwise → keep standalone
		"""
		if not chunks:
			return []

		MIN_SECTION_SIZE = 200  # section start < this → merge forward

		merged: List[Dict] = []
		for chunk in chunks:
			text = chunk.get("text", "").strip()
			metadata = chunk.get("metadata", {}).copy()

			if not text:
				continue

			if not merged:
				merged.append({"text": text, "metadata": metadata})
				continue

			prev = merged[-1]
			prev_text = prev["text"]

			# Fix dropped-tail: "Mẫu số:", "Phụ lục:" — attach next sentence
			if self._ends_with_connector(prev_text):
				moved, remaining = self._take_until_nearest_period(text)
				if moved:
					prev["text"] = f"{prev_text} {moved}"
					prev["metadata"]["header"] = self._extract_header(prev["text"])
				text = remaining
				if not text:
					continue

			is_section = self._looks_like_section_start(text)

			# Substantial section start → keep standalone
			if is_section and len(text) >= MIN_SECTION_SIZE:
				merged.append({"text": text, "metadata": metadata})
			# Short section start → merge into previous if possible
			elif is_section and len(text) < MIN_SECTION_SIZE:
				if len(prev["text"]) + len(text) <= max_chunk_size:
					prev["text"] = f"{prev['text']}\n{text}"
				else:
					merged.append({"text": text, "metadata": metadata})
			# Weak chunk → merge into previous if not too large
			elif self._is_weak_chunk(text) and len(prev["text"]) + len(text) <= max_chunk_size:
				prev["text"] = f"{prev['text']}\n{text}"
			else:
				merged.append({"text": text, "metadata": metadata})

		# Second pass: merge any remaining short chunks forward
		if len(merged) > 1:
			final: List[Dict] = [merged[0]]
			for chunk in merged[1:]:
				text = chunk["text"]
				if len(text) < MIN_SECTION_SIZE and len(final[-1]["text"]) + len(text) <= max_chunk_size:
					final[-1]["text"] = f"{final[-1]['text']}\n{text}"
				else:
					final.append(chunk)
			merged = final

		return merged

	# ═══════════════════════════════════════════
	# HELPERS
	# ═══════════════════════════════════════════

	def _split_by_positions(self, text: str, pattern: re.Pattern) -> List[str]:
		"""Split by match positions to preserve full text content."""
		matches = list(pattern.finditer(text))
		if len(matches) < 2:
			return [text]

		starts = [m.start() for m in matches]
		if starts[0] != 0:
			starts = [0] + starts

		parts: List[str] = []
		for idx, start in enumerate(starts):
			end = starts[idx + 1] if idx + 1 < len(starts) else len(text)
			piece = text[start:end]
			if piece.strip():
				parts.append(piece)

		return parts if parts else [text]

	def _extract_header(self, text: str) -> str:
		lines = [line.strip() for line in text.split("\n") if line.strip()]
		if not lines:
			return ""

		first_line = lines[0]
		# Strip markdown heading marker for cleaner header
		if first_line.startswith('#'):
			first_line = first_line.lstrip('#').strip()

		return first_line[:120]

	def find_first_priority_pattern_position(self, text: str) -> int:
		"""Find the starting position of the first priority pattern match.
		Used by metadata extractor to determine where body content starts.
		"""
		for name, pattern in self.patterns:
			match = pattern.search(text)
			if match:
				return match.start()
		return len(text)
