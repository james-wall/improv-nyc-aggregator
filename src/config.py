"""Shared Gemini model configuration.

One place to bump model ids when Google retires a model (the old 2.0 flash model
started returning 404 in Oct 2026 and silently broke performer enrichment).
"""

# Primary model for newsletter curation.
GEMINI_MODEL = "gemini-2.5-flash"

# Cheaper model tried when the primary is rate-limited / out of quota (429),
# overloaded (503) or returns unusable output. Quota is tracked per model, so
# this often still works when the primary's quota is exhausted.
GEMINI_FALLBACK_MODEL = "gemini-2.5-flash-lite"

# Performer enrichment runs just before curation. The free-tier key allows
# 5 requests/minute *per model*, so enriching on GEMINI_MODEL used up
# curation's quota (draft run 39701631510: 1 performer enriched, curation
# 429'd). Keep enrichment on a different model so the two never compete.
ENRICHER_MODEL = "gemini-2.5-flash-lite"

# 2.5-flash counts thinking tokens against max_output_tokens; an unbounded
# thinking budget truncated the curated JSON on 2026-10-18. Cap it.
CURATION_THINKING_BUDGET = 2048
CURATION_MAX_OUTPUT_TOKENS = 32768
