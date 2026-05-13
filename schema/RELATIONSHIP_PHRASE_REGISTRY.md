# Relationship Phrase Registry

Purpose: deterministic phrase governance for relationship extraction.

This registry maps approved linguistic variants to explicit predicates and confidence tiers.

MrLore extraction rules:
- Registry phrases are deterministic only.
- Extractors may emit candidates only.
- No extractor may promote canon.
- No extractor may edit Tier 0 prose.
- Ambiguous phrases must remain medium or low confidence.
- Unanchored subjects or targets must be filtered.

| Phrase | Predicate | Confidence | Context |
|---|---|---|---|
| is a member of | member_of | high | explicit membership |
| belongs to | member_of | high | explicit membership |
| part of | member_of | high | explicit membership |
| served under | member_of | medium | allegiance/service |
| serves under | member_of | medium | allegiance/service |
| sworn to | member_of | medium | oath/binding |
| under the banner of | member_of | medium | factional alignment |
| of the | member_of | low | origin/affiliation |
