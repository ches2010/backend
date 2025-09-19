from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api import proxy, server, settings

app = FastAPI(title="Proxy Manager API", version="1.0.0")

# 配置 CORS，允许前端访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应替换为具体的前端域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(proxy.router, prefix="/api/proxy", tags=["Proxy Management"])
app.include_router(server.router, prefix="/api/server", tags=["Server Control"])
app.include_router(settings.router, prefix="/api/settings", tags=["Settings"])

@app.get("/")
async def root():
    return {"message": "Welcome to Proxy Manager API"}
