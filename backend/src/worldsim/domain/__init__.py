"""Domain contracts: pure world truth (owned by S0-DOM-001).

Rules:

- imports only the standard library and Pydantic v2, the explicitly
  approved validation primitive (strict parsing, forbidden extra fields,
  generated JSON Schema);
- no ORM, HTTP, provider, graph, or infrastructure imports;
- frozen immutable models; state changes arrive as new versions, never
  mutation.
"""
