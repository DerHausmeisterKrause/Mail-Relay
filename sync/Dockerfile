FROM debian:12-slim
RUN apt-get update && apt-get install -y --no-install-recommends rsync openssh-client curl jq iproute2 docker.io util-linux && rm -rf /var/lib/apt/lists/*
COPY queue-sync.sh /queue-sync.sh
RUN chmod +x /queue-sync.sh
CMD ["/queue-sync.sh"]
