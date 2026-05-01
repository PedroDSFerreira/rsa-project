import docker

_client = docker.from_env()


def _exec(container_name: str, cmd: str):
    container = _client.containers.get(container_name)
    container.exec_run(cmd)


def block(container_name: str, mac: str):
    _exec(container_name, f"block {mac}")


def unblock(container_name: str, mac: str):
    _exec(container_name, f"unblock {mac}")


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
        elif not should_connect and was_connected:
            block(a, mac_b)
            block(b, mac_a)
            self._state[key] = False

    def connected_pairs(self) -> list[tuple[str, str]]:
        return [pair for pair, connected in self._state.items() if connected]
