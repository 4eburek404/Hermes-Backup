def format_labels(labels: list[str]) -> str:
    cleaned = [label.strip() for label in labels if label.strip()]
    return ", ".join(cleaned)
