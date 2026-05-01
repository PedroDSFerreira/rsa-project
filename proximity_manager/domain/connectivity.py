from infra.mac_filter import block, unblock


class ConnectivityMatrix:
    def __init__(self):
        self._state: dict[tuple[str, str], bool] = {}

    def _key(self, a: str, b: str) -> tuple[str, str]:
        return (min(a, b), max(a, b))

    def is_connected(self, a: str, b: str) -> bool:
        return self._state.get(self._key(a, b), False)

    def update(self, a: str, b: str, mac_a: str, mac_b: str, should_connect: bool):
        key = self._key(a, b)
        was_connected = self._state.get(key, False)

        if should_connect and not was_connected:
            unblock(a, mac_b)
            unblock(b, mac_a)
            self._state[key] = True
        elif not should_connect:
            block(a, mac_b)
            block(b, mac_a)
            self._state[key] = False

    def seed_blocked(self, a: str, b: str):
        self._state[self._key(a, b)] = False
