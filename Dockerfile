FROM python:3.12 as pythonbase

FROM pythonbase as devtest_builder
# These are used by installer script.
ARG PYVER
ARG VERSION
ARG PYPI_REPO
ARG PYPI_HOST
SHELL ["/bin/bash", "-c"]

RUN apt-get -y update && apt-get install -y build-essential cmake gcc \
	libusb-1.0-0-dev postgresql-client libpq-dev
WORKDIR /build
COPY dev-requirements.txt docker_installer.sh dist/*.tar.gz /build/

ENV LANG=C.UTF-8 PYVER=${PYVER} \
	PYPI_REPO=${PYPI_REPO} PYPI_HOST=${PYPI_HOST} \
	VERSION=${VERSION}
RUN ["/bin/bash", "docker_installer.sh"]

FROM pythonbase

# Add some extra system stuff that every good test framework needs.
ENV LANG=en_US.UTF-8 TZ=America/Los_Angeles USER=tester \
	PYTHON_DEBUGGER=elicit.debugger PYTHONWARNINGS=ignore
RUN apt-get -y update && DEBIAN_FRONTEND="noninteractive" apt-get install -y \
	tzdata fping usbutils lsb-release vim-nox libusb-1.0 libpq5
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone
# This framework needs a real user.
RUN useradd -U -u 1000 -m tester
RUN mkdir -p /home/tester/.config/devtest
RUN mkdir -p /home/tester/tmp/resultsdir  # Need volume mount here
COPY  $HOME/.config/devtest/config_docker.yaml /home/tester/.config/devtest/config.yaml
# Installer script put everything we need under /install
COPY --from=devtest_builder /install /usr/local

USER tester:tester
WORKDIR /home/tester
ENTRYPOINT [ "devtester"]
