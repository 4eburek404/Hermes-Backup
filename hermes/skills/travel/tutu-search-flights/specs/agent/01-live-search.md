# Agent specification — successful live flight search

This specification is independent of the offline product specification in
[`../02-successful-search.md`](../02-successful-search.md). It covers the
observable behavior from user request to answer, not Python parsing or data
model internals.

## Scenario

**Given** a user asks for a simple one-way flight on a route and future date
supported by Tutu, Tutu MCP is enabled in the installed Hermes runtime, and the
`tutu-search-flights` skill is active.

**When** the Hermes agent handles that request.

**Then**

- It obtains offers by calling the native Tutu MCP flight-search tool.
- Any flight, price, fare, or condition stated in the answer is supported by the
  returned MCP result; the model does not invent missing values.
- The answer is grounded in the MCP result and is delivered to the user after a
  successful simple search.
- The agent does not use the research `probe.py` or another transport as the
  production search path, and does not use a project plugin to intercept the
  MCP result.
- For this simple scenario it does not make alternative searches without a
  reason in the request or the preceding result.

## Evaluation evidence

Evaluate **outcome** and **trajectory** separately. Use the recorded MCP result
as the source of truth: compare every concrete claim in the final answer with
that result and preserve missing fields as unknown. For trajectory, verify the
native MCP tool call, its actual arguments and result, subsequent actions, and
that no alternate transport or plugin interception was used. Live dates,
offers, carriers, fares, and prices are observations, never fixed expectations.

Run this specification through the shared agent-evaluation harness. Keep it out
of `make spec` and `make check`; those commands cover deterministic,
fixture-based product behavior only.
