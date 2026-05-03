FROM ghcr.io/nap-it/vanetza-nap:latest

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip3 install --no-cache-dir \
    --trusted-host pypi.org \
    --trusted-host files.pythonhosted.org \
    -r requirements.txt

COPY init.sh /init.sh
RUN chmod +x /init.sh
COPY main.py .

ENTRYPOINT ["/init.sh"]
