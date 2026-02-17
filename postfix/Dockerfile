FROM debian:12-slim
RUN apt-get update && apt-get install -y --no-install-recommends postfix rsyslog ca-certificates && rm -rf /var/lib/apt/lists/*
COPY main.cf /etc/postfix/main.cf
COPY master.cf /etc/postfix/master.cf
COPY entrypoint.sh /entrypoint.sh
COPY policy-check.sh /usr/local/bin/policy-check.sh
RUN chmod +x /entrypoint.sh /usr/local/bin/policy-check.sh
CMD ["/entrypoint.sh"]
