ARG BUILD_FROM
FROM ${BUILD_FROM}

RUN apk add --no-cache python3 py3-pip py3-requests py3-pillow nginx jq tzdata font-dejavu

ENV TZ=America/Chicago

COPY rootfs/run.sh /run.sh
COPY rootfs/app /app
COPY rootfs/nginx.conf /etc/nginx/nginx.conf
COPY assets /app/assets

# Strip Windows CRLF that breaks #!/bin/bash shebang
RUN sed -i 's/\r$//' /run.sh \
    && chmod +x /run.sh \
    && mkdir -p /run/nginx /var/lib/nginx/tmp /var/log/nginx /app/www

WORKDIR /app

CMD [ "/run.sh" ]
