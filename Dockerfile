FROM python:3.12-slim

WORKDIR /app

COPY src ./src

ENV PYTHONUNBUFFERED=1
EXPOSE 8080

CMD ["python", "-m", "src.rtsp_webrtc_api"]
