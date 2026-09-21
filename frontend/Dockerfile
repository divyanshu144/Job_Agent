FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
ARG NGINX_CONF=nginx.prod.conf
# Rendered by the nginx image's envsubst entrypoint into conf.d/default.conf. Only
# variables that are set in the environment are substituted, so the existing configs
# (no ${...}) pass through untouched and nginx's own $vars are safe.
COPY ${NGINX_CONF} /etc/nginx/templates/default.conf.template
# Defaults used only by nginx.railway.conf.template (select it with the NGINX_CONF
# build arg). Railway injects PORT itself; DNS_RESOLVER is its private-network DNS.
ENV PORT=80 \
    API_UPSTREAM=api.railway.internal:8000 \
    DNS_RESOLVER=[fd12::10]
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://127.0.0.1:${PORT}/healthz >/dev/null || exit 1
