from identity import own_ip, resolve
from sensor import SensorAgent

if __name__ == "__main__":
    SensorAgent(resolve(), ip=own_ip()).run()
