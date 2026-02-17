FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/nginx.conf
COPY src /usr/share/nginx/html
CMD ["nginx", "-g", "daemon off;"]
