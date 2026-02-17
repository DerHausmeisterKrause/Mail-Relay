FROM nginx:1.27-alpine
RUN apk add --no-cache openssl
COPY nginx.conf /etc/nginx/nginx.conf
COPY src /usr/share/nginx/html
COPY entrypoint.sh /entrypoint.sh
CMD ["/entrypoint.sh"]
