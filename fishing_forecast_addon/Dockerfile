ARG BUILD_FROM
FROM ${BUILD_FROM}

RUN apk add --no-cache python3 py3-pip py3-requests

COPY rootfs/run.sh /run.sh
COPY rootfs/app /app

RUN chmod +x /run.sh

WORKDIR /app

CMD [ "/run.sh" ]
