FROM debian:12-slim
RUN apt-get update && apt-get install -y --no-install-recommends keepalived iproute2 curl jq ca-certificates && rm -rf /var/lib/apt/lists/*
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
CMD ["/entrypoint.sh"]
