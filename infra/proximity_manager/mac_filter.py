import docker

_client = docker.from_env()

# Set to False on first ebtables failure (e.g. WSL2 / nf_tables kernel).
# When disabled, MAC filtering is skipped; drones enforce proximity via sim/links.
_ebtables_supported = True


def _exec(container_name: str, cmd: list[str]) -> str:
    global _ebtables_supported
    if not _ebtables_supported:
        return ""
    try:
        container = _client.containers.get(container_name)
    except docker.errors.NotFound:
        print(f"[exec] container not found: {container_name}", flush=True)
        return ""
    result = container.exec_run(cmd)
    output = result.output.decode().strip() if result.output else ""
    if result.exit_code not in (0, 1):
        if "TABLE_ADD failed" in output or "Operation not supported" in output:
            _ebtables_supported = False
            print(
                "[mac_filter] ebtables kernel modules not loaded (run: "
                "docker run --rm --privileged -v /lib/modules:/lib/modules alpine "
                "sh -c 'modprobe ebtables && modprobe ebtable_filter'). "
                "MAC-level filtering disabled — drones will enforce proximity via sim/links.",
                flush=True,
            )
        elif output:
            print(f"[exec {container_name}] exit={result.exit_code}: {output}", flush=True)
    return output


def block(container_name: str, mac: str):
    _exec(container_name, ["block", mac])


def unblock(container_name: str, mac: str):
    _exec(container_name, ["unblock", mac])


def filter_present(container_name: str, mac: str) -> bool:
    if not _ebtables_supported:
        return False
    out = _exec(container_name, ["ebtables", "-L"])
    return mac.lower() in out.lower()
