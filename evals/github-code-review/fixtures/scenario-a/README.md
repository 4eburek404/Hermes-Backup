# Allocation fixture

Public contract: `allocate(total_cents, buckets)` rejects negative totals and
non-positive bucket counts. For valid input it returns exactly `buckets`
non-negative integer shares summing to `total_cents`; remainder cents go to the
first shares (`allocate(10, 3) == [4, 3, 3]`).
