import docker

_client = docker.from_env()

IFACE = "br0"


def _exec(container_name: str, cmd: str) -> str:
    container = _client.containers.get(container_name)
    result = container.exec_run(["sh", "-c", cmd])
    output = result.output.decode().strip() if result.output else ""
    if result.exit_code != 0 and output:
        print(f"[exec {container_name}] exit={result.exit_code}: {output}", flush=True)
    return output


def _ensure_ingress(container_name: str):
    """Add the ingress qdisc if it doesn't already exist (idempotent)."""
    _exec(container_name, f"tc qdisc add dev {IFACE} ingress 2>/dev/null || true")


def block(container_name: str, mac: str):
    """Drop all frames arriving on br0 from the given source MAC. Idempotent."""
    _ensure_ingress(container_name)
    handle = int(mac.replace(":", ""), 16) % 65535 + 1
    _exec(
        container_name,
        f"tc filter replace dev {IFACE} parent ffff: protocol all"
        f" prio {handle} handle {handle} flower src_mac {mac} action drop 2>/dev/null || true",
    )


def filter_present(container_name: str, mac: str) -> bool:
    """Return True if a drop filter for this MAC exists on br0 ingress."""
    handle = int(mac.replace(":", ""), 16) % 65535 + 1
    out = _exec(container_name, f"tc filter show dev {IFACE} parent ffff: prio {handle} 2>/dev/null")
    return mac.lower() in out.lower()


def unblock(container_name: str, mac: str):
    """Remove the drop filter for the given source MAC."""
    handle = int(mac.replace(":", ""), 16) % 65535 + 1
    _exec(
        container_name,
        f"tc filter del dev {IFACE} parent ffff: prio {handle} 2>/dev/null || true",
    )


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
            # Always re-enforce the block so vanetza startup can't wipe our filters
            block(a, mac_b)
            block(b, mac_a)
            self._state[key] = False

    def connected_pairs(self) -> list[tuple[str, str]]:
        return [pair for pair, connected in self._state.items() if connected]

