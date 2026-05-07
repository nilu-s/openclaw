FROM ghcr.io/openclaw/openclaw:latest

USER root

RUN apt-get update \
     && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
     ca-certificates \
     curl \
     git \
     gh \
     jq \
     openssh-client \
     python3-pip \
     && rm -rf /var/lib/apt/lists/*

COPY nexusctl-pkg/ /tmp/nexusctl-pkg/

RUN pip install --break-system-packages --no-cache-dir /tmp/nexusctl-pkg/ \
     && rm -rf /tmp/nexusctl-pkg/

RUN gh --version > /dev/null 2>&1 \
     && git --version > /dev/null 2>&1 \
     && ssh -V > /dev/null 2>&1 \
     && nexusctl --help > /dev/null 2>&1 \
     && nexusctl-server --help > /dev/null 2>&1

USER node

WORKDIR /workspace