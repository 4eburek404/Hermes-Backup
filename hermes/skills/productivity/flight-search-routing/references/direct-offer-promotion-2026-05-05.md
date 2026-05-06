# Direct-offer promotion when assembled ranking omits nonstop

Session calibration: `SVX → PKX`, one-way `2026-08-05`, exact destination `PKX` / Beijing Daxing.

## Problem pattern

`route kb-assemble` is useful for ranked one-stop/separate-ticket alternatives, but a nonstop can appear in live aggregate or carrier-filtered search and still be absent from `data.ranked` if the assembly frontier is focused on segment combinations. If the agent recommends only from assembled ranking, it can miss the operationally dominant option.

## Required handling

When the request is exact-airport and business-travel oriented:

1. Search or inspect live aggregate offers for nonstop/direct candidates before final ranking.
2. If a plausible direct candidate exists, verify it with a carrier-filtered or airline-specific query when possible.
3. Compare direct candidates against assembled `data.ranked` alternatives using business value:
   - exact destination airport;
   - no connection risk;
   - elapsed time;
   - arrival time/day;
   - price delta versus viable one-stop options;
   - carrier/tariff caveats.
4. If the direct option dominates, promote it as the main recommendation even if it is not `data.ranked[0]`; explicitly attribute its source as live aggregate/carrier-filtered, not as assembled rank.
5. Use `data.ranked` for structured one-stop alternatives and `data.rejected_pairs`/raw aggregate offers to explain why cheap options were demoted.

## Example outcome

For `SVX → PKX 2026-08-05`:

- Direct found in live aggregate and U6-filtered search:
  - `U6775 SVX 2026-08-05 00:40 +05 → PKX 2026-08-05 09:55 +08`
  - price hint around `38 405 RUB` in aggregate;
  - elapsed `6ч15`;
  - no connection risk.
- Best one-stop alternatives were S7 via `IKT/OVB` around `36–41k RUB`, `10ч40–12ч10`, arrival early next day.
- SVO/MU/CZ alternatives had safe buffers but were longer and more expensive.
- Cheap EY/AUH offers around `30–35k RUB` were not business-first due very long elapsed times and/or Moscow cross-airport mismatch (`VKO/DME → SVO`).

Conclusion: recommend the direct exact-`PKX` flight first when baggage/tariff checks pass; present one-stop alternatives only as fallbacks.
