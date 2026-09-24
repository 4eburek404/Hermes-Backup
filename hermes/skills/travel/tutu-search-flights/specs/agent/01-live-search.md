# Agent specification — successful live flight search

This specification is independent of the offline product specification in
[`../02-successful-search.md`](../02-successful-search.md). It covers the
observable behavior from user request to answer and the production transport
used for the live call.

## Scenario

**Given** a user asks for a simple one-way flight on a route and future date
supported by Tutu, and the `tutu-search-flights` skill is active.

**When** the Hermes agent handles that request.

**Then**

- It performs the live search through the project's MCP SDK client against
  `https://mcp.tutu.ru/mcp`.
- The SDK session calls `search_avia` with arguments matching the user's request.
- Any flight, price, fare, or condition stated in the answer is supported by the
  returned Tutu result; the model does not invent missing values.
- The answer is grounded in that result and is delivered after the successful
  search.
- The agent does not use the native Hermes Tutu MCP tool, research `probe.py`,
  HTTP/curl, or another transport as the production search path.
- For this simple scenario it does not make alternative searches without a
  reason in the request or the preceding result.

## Evaluation evidence

Evaluate **outcome** and **trajectory** separately. For outcome, compare every
concrete claim in the final answer with the live SDK result and preserve missing
fields as unknown. For trajectory, verify the SDK-backed live-search command,
its actual arguments and result, and that no native Tutu MCP tool, probe, curl,
or alternative search path was used.

Live dates, offers, carriers, fares, and prices are observations, never fixed
expectations. Run this specification through the shared agent-evaluation
harness. Keep it out of `make spec` and `make check`; deterministic product
behavior remains fixture-based.
