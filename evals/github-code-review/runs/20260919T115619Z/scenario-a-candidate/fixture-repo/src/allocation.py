def allocate(total_cents: int, buckets: int) -> list[int]:
    if total_cents < 0 or buckets < 0:
        raise ValueError("total and buckets must be positive")
    return [total_cents // buckets] * buckets
