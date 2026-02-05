#============
# LEGAL-INFO
#============
# Disclaimer:
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    any later version.
#    This script is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY.
#
# Copyright: 2025 Massimo Fares, INGV - Italy <massimo.fares@ingv.it>; EIDA Italia Team, INGV - Italy  <adaisacd.ont@ingv.it>
# License: GPLv3
# Platform: Linux
# Author: Massimo Fares, INGV - Italy <massimo.fares@ingv.it>

#---------------------------------------------------------------
# Dockerized BASE for tornado PID-LAND the INGV PID Landing service
# Based on ubuntu:20.04
#
# Description:
# BASE Modules: MONGO and TORNADO in python 3
#
# imageName:'base-landing:1.3'
#
# build:
# build command: sudo docker build -t "base-landing:1.3" .
#
# Use: docker run: use a docker compose file

FROM ubuntu:20.04
LABEL maintainer="massimo.fares@ingv.it"

ARG PUID=1000
ARG PGID=1000
ARG USER=sysop

# Non-root user
RUN groupadd -g ${PGID} ${USER} && \
    useradd -u ${PUID} -g ${USER} -m -s /bin/bash ${USER}

# Dependencies
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    python3 python3-pip python3-dev python3-setuptools \
    python3-psutil python3-requests python3-jsonschema \
    libfuse2 libcurl4-gnutls-dev libssl-dev pkg-config \
    git vim wget rsync net-tools iputils-ping sudo nano \
    procps less libxml2-dev libxslt1-dev libz-dev libfreetype6-dev \
    python3-numpy python3-scipy python3-matplotlib \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

# Python packages
RUN pip3 install --no-cache-dir pymongo pyyaml tornado pyshacl rdflib jsonschema
RUN pip3 install --upgrade jsonschema

# Directories
RUN mkdir -p /usr/src/code /var/lib/archive && \
    chown -R ${USER}:${USER} /usr/src/code /var/lib/archive

WORKDIR /usr/src/code
EXPOSE 8888

USER ${USER}

# Tornado entrypoint
#CMD ["python3", "pid_land.py"]
