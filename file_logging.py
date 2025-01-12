def log_event(event):
    if "changed_state" in event and event["changed_state"]:
        print("State changed: ", event)

    if "turned_critical" in event and event["turned_critical"]:
        print("Event turned critical: ", event)

    print("Event: ", event)