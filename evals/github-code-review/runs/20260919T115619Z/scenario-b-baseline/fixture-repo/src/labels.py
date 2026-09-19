def format_labels(labels: list[str], *, sort: bool = False) -> str:
    cleaned = [label.strip() for label in labels if label.strip()]
    if sort:
        cleaned.sort(key=str.casefold)
    return ", ".join(cleaned)
