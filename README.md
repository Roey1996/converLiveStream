# converLiveStream

一个最小可用的 RTSP 转 WebRTC 服务。接口接收 RTSP 地址，动态注册到 MediaMTX，然后返回浏览器可直接打开的 WebRTC 播放地址。

## 启动

### 本地启动

下载 MediaMTX 二进制到 `.local/bin/mediamtx` 后执行：

```bash
chmod +x scripts/start-local.sh
./scripts/start-local.sh
```

### Docker 启动

```bash
docker compose up --build
```

默认端口：

- API: `http://localhost:8236`
- WebRTC: `http://localhost:8237`
- WebRTC ICE/UDP: `8189/udp`
- RTSP: `rtsp://localhost:8554`

MediaMTX 的控制 API 只在 Docker 内部网络暴露，由本项目 API 服务调用。

## 创建转换流

```bash
curl -X POST http://localhost:8236/api/streams \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "camera01",
    "rtspUrl": "rtsp://user:pass@192.168.1.10:554/stream1",
    "sourceOnDemand": true,
    "rtspTransport": "tcp"
  }'
```

返回示例：

```json
{
  "name": "camera01",
  "rtspUrl": "rtsp://user:pass@192.168.1.10:554/stream1",
  "webrtcUrl": "http://localhost:8237/camera01",
  "whepUrl": "http://localhost:8237/camera01/whep",
  "statusUrl": "/api/streams/camera01",
  "sourceOnDemand": true,
  "rtspTransport": "tcp"
}
```

浏览器打开 `webrtcUrl` 即可播放。支持 WHEP 的客户端可使用 `whepUrl`。

## 查询流状态

```bash
curl http://localhost:8236/api/streams/camera01
```

## 删除流

```bash
curl -X DELETE http://localhost:8236/api/streams/camera01
```

## 说明

MediaMTX 会把配置里的 RTSP source 暴露成 WebRTC。根据 MediaMTX 文档，WebRTC 浏览器播放地址格式为 `http://localhost:8237/{path}`，WHEP 地址格式为 `http://localhost:8237/{path}/whep`。
