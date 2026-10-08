def encode_event(event: dict) -> dict:
    return {"id": event["id"], "type": event["type"], "payload": event["payload"]}
