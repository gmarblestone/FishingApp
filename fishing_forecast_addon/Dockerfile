ARG BUILD_FROM
FROM ${BUILD_FROM}

RUN apk add --no-cache python3 py3-pip py3-requests nginx

COPY rootfs/run.sh /run.sh
COPY rootfs/app /app
COPY rootfs/nginx.conf /etc/nginx/nginx.conf

RUN chmod +x /run.sh \
    && mkdir -p /run/nginx /var/lib/nginx/tmp /app/www

WORKDIR /app

CMD [ "/run.sh" ]
