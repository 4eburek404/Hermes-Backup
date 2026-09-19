def encode_event(event: dict, *, include_metadata: bool = False) -> dict:
    result = {"id": event["id"], "type": event["type"], "payload": event["payload"]}
    if include_metadata:
        result["metadata"] = event.get("metadata", {})
    return result
