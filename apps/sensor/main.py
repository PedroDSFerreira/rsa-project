import time

from identity import own_ip, resolve
from sensor import SensorAgent

if __name__ == "__main__":
    while True:
        try:
            identity = resolve()
            ip = own_ip()
            break
        except Exception as e:
            print(f"Startup failed: {e} — retrying in 2s", flush=True)
            time.sleep(2)
    SensorAgent(identity, ip=ip).run()
