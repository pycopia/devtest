import selectors

EventLoop = selectors.DefaultSelector


def get_event_loop() -> EventLoop:
    ...
