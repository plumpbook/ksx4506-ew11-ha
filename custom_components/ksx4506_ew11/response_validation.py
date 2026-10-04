"""Conservative evidence checks for new identities and status-query replies."""


def valid_response_payload(addr: int, cmd: int, payload: bytes) -> bool:
    if not payload:
        return False
    if addr == 0x12 and cmd in (0x81, 0xC1):
        # KS X gas response: error + status, with reserved high status bits.
        return len(payload) == 2 and not (payload[1] & 0xE0)
    if addr == 0x0E and cmd in (0x81, 0xC1):
        # Lighting: error + up to fourteen channel states; bits 2/3 reserved.
        return 2 <= len(payload) <= 15 and all(
            not (state & 0x0C) and (not (state & 0xF0) or bool(state & 0x02))
            for state in payload[1:]
        )
    return True
