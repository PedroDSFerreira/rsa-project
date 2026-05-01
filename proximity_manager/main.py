import os

from infra.config import load_config
from manager import ProximityManager

CONFIG_PATH = os.getenv("CONFIG_PATH", "/config/simulation_config.yaml")

if __name__ == "__main__":
    ProximityManager(load_config(CONFIG_PATH)).run()
