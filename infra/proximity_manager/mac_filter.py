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
    _exec(container_name, f"tc qdisc add dev {IFACE} ingress 2>/dev/null || true")


def _handle(mac: str) -> int:
    return int(mac.replace(":", ""), 16) % 65535 + 1


def block(container_name: str, mac: str):
    _ensure_ingress(container_name)
    handle = _handle(mac)
    _exec(
        container_name,
        f"tc filter replace dev {IFACE} parent ffff: protocol all"
        f" prio {handle} handle {handle} flower src_mac {mac} action drop 2>/dev/null || true",
    )


def unblock(container_name: str, mac: str):
    handle = _handle(mac)
    _exec(
        container_name,
        f"tc filter del dev {IFACE} parent ffff: prio {handle} 2>/dev/null || true",
    )


def filter_present(container_name: str, mac: str) -> bool:
    handle = _handle(mac)
    out = _exec(container_name, f"tc filter show dev {IFACE} parent ffff: prio {handle} 2>/dev/null")
    return mac.lower() in out.lower()
