from contextlib import asynccontextmanager

from fastapi import FastAPI

import mqtt_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    mqtt_client.start()
    yield


app = FastAPI(lifespan=lifespan)
