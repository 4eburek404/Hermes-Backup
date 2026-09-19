def allocate(total_cents: int, buckets: int) -> list[int]:
    if total_cents < 0 or buckets <= 0:
        raise ValueError("total and buckets must be positive")
    quotient, remainder = divmod(total_cents, buckets)
    return [quotient + (index < remainder) for index in range(buckets)]
