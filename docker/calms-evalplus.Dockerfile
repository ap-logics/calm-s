FROM python:3.12-slim
# Build with calms_data/code-runtime as context, created by prepare_code_runtime.py.
COPY evalplus /opt/evalplus
RUN pip install --no-cache-dir numpy psutil datasets wget tempdir appdirs
RUN pip freeze > /opt/python-requirements.txt
COPY evalplus_check.py /opt/evalplus_check.py
ENV PYTHONPATH=/opt/evalplus
ENV OPENBLAS_NUM_THREADS=1
USER 65534:65534
WORKDIR /tmp
ENTRYPOINT ["python", "-B", "/opt/evalplus_check.py"]
