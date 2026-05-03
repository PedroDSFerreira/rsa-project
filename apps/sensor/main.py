from identity import own_ip, resolve
from sensor import SensorAgent

if __name__ == "__main__":
    identity = resolve()
    agent = SensorAgent(identity, ip=own_ip())
    agent.announce()
    agent.run()
