"""
Milestone 3 (implemented): heuristic structure detection + cross-page
continuity.

See detector.py for classify_page(page) -> list[StructureElement] and
detect_sections(elements_by_page) -> list[Section]. Deterministic
regex/word-shape heuristics, no LLM call — see detector.py's module
docstring for why, and README's "Known limitations" for where this
will get things wrong on a real book.
"""
