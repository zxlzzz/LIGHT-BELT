"""
LIGHT-BELT Host Service 入口。
相当于 Spring Boot 的 main() + @SpringBootApplication。

启动方式：
  cd host_service
  python main.py

本地 Postman 测试地址：
  REST:      http://localhost:8443/api/v1/status
  WebSocket: ws://localhost:8443/ws?ticket=<ticket>
"""

import uvicorn
from fastapi import FastAPI
from .config import HOST, PORT, ENABLE_TLS, TLS_CERTFILE, TLS_KEYFILE

app = FastAPI(title="LIGHT-BELT Host Service", version="1.0")

# ── 注册路由，相当于 @ComponentScan ──
from .routers import status, auth, state, shows, capabilities
from .routers import playback, lights, effects, audio, scenes
from . import ws

app.include_router(status.router)
app.include_router(auth.router)
app.include_router(state.router)
app.include_router(shows.router)
app.include_router(capabilities.router)
app.include_router(playback.router)
app.include_router(lights.router)
app.include_router(effects.router)
app.include_router(audio.router)
app.include_router(scenes.router)
app.include_router(ws.router)


def run():
    scheme = "https" if ENABLE_TLS else "http"
    print(f"Host Service starting on {scheme}://{HOST}:{PORT}")
    print(f"REST:   {scheme}://localhost:{PORT}/api/v1/status")
    print(f"Swagger: {scheme}://localhost:{PORT}/docs")
    kwargs: dict = {"host": HOST, "port": PORT}
    if ENABLE_TLS:
        kwargs["ssl_certfile"] = TLS_CERTFILE
        kwargs["ssl_keyfile"] = TLS_KEYFILE
    uvicorn.run(app, **kwargs)


if __name__ == "__main__":
    run()
