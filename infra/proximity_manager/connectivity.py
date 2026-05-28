from entity import Entity
from mac_filter import block, unblock


class ConnectivityMatrix:
    def __init__(self):
        self._state: dict[tuple[str, str], bool] = {}

    def _key(self, a: str, b: str) -> tuple[str, str]:
        return (min(a, b), max(a, b))

    def update(self, a: Entity, b: Entity, should_connect: bool):
        key = self._key(a.container_name, b.container_name)
        was_connected = self._state.get(key, False)

        if should_connect and not was_connected:
            if a.has_vanetza and b.has_vanetza:
                unblock(a.container_name, b.mac)
                unblock(b.container_name, a.mac)
            self._state[key] = True
        elif not should_connect and was_connected:
            if a.has_vanetza and b.has_vanetza:
                block(a.container_name, b.mac)
                block(b.container_name, a.mac)
            self._state[key] = False

    def seed_blocked(self, a: str, b: str):
        self._state[self._key(a, b)] = False
