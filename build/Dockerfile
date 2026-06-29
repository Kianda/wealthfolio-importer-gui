FROM python:3.12-slim

WORKDIR /app

COPY build/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY build/src ./src
COPY build/tests ./tests
COPY build/pyproject.toml ./
COPY build/app.py ./

EXPOSE 23527
CMD ["streamlit", "run", "app.py", \
     "--server.port=23527", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]
