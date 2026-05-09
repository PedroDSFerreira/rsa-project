import docker

_client = docker.from_env()


def _exec(container_name: str, cmd: list[str]) -> str:
    try:
        container = _client.containers.get(container_name)
    except docker.errors.NotFound:
        print(f"[exec] container not found: {container_name}", flush=True)
        return ""
    result = container.exec_run(cmd)
    output = result.output.decode().strip() if result.output else ""
    if result.exit_code not in (0, 1) and output:
        print(f"[exec {container_name}] exit={result.exit_code}: {output}", flush=True)
    return output


def block(container_name: str, mac: str):
    _exec(container_name, ["block", mac])


def unblock(container_name: str, mac: str):
    _exec(container_name, ["unblock", mac])


def filter_present(container_name: str, mac: str) -> bool:
    out = _exec(container_name, ["ebtables", "-L"])
    return mac.lower() in out.lower()
