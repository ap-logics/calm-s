FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git build-essential && rm -rf /var/lib/apt/lists/*
COPY appworld /opt/appworld-source
RUN pip install --no-cache-dir /opt/appworld-source
RUN appworld install
ENV APPWORLD_ROOT=/world
RUN mkdir /world
WORKDIR /world
RUN appworld download data --root /world
RUN pip freeze > /opt/python-requirements.txt
COPY appworld_smoke.py /opt/appworld_smoke.py
RUN useradd --uid 10001 --create-home experiment && chown -R experiment:experiment /world
USER 10001:10001
WORKDIR /world
CMD ["python", "-B", "/opt/appworld_smoke.py"]
