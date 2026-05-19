from drone.agent import DroneAgent
from drone.config import DroneConfig

if __name__ == "__main__":
    config = DroneConfig.from_env()
    agent = DroneAgent(config)
    agent.connect()
    agent.announce()
    agent.run()
