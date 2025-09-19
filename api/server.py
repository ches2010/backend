from fastapi import APIRouter, Depends
from ..schemas import *
from ..core.server import ProxyServer
from ..core.rotator import ProxyRotator
import threading

router = APIRouter()

# 全局实例
server_instance = None
rotator_instance = ProxyRotator() # 与 proxy.py 共享同一个实例

@router.post("/start", response_model=SuccessResponse)
async def start_server(request: StartServerRequest):
    """启动 HTTP 和 SOCKS5 代理服务"""
    global server_instance
    if server_instance and server_instance._running:
        return SuccessResponse(success=False, message="服务已在运行中。")
    
    server_instance = ProxyServer(
        http_host="127.0.0.1",
        http_port=request.http_port,
        socks5_host="127.0.0.1",
        socks5_port=request.socks5_port,
        rotator=rotator_instance,
        log_queue=server_instance._log_queue if server_instance else queue.Queue() # 简化处理
    )
    server_instance.start_all()
    
    return SuccessResponse(success=True, message=f"代理服务已启动。HTTP: {request.http_port}, SOCKS5: {request.socks5_port}")

@router.post("/stop", response_model=SuccessResponse)
async def stop_server():
    """停止代理服务"""
    global server_instance
    if not server_instance or not server_instance._running:
        return SuccessResponse(success=False, message="服务未在运行。")
    
    server_instance.stop_all()
    server_instance = None
    
    return SuccessResponse(success=True, message="代理服务已停止。")

@router.post("/set_rotation_mode", response_model=SuccessResponse)
async def set_rotation_mode(mode: RotationMode):
    """设置轮换模式"""
    global server_instance
    if not server_instance:
        return SuccessResponse(success=False, message="请先启动服务。")
    
    server_instance.set_rotation_mode(mode.per_request)
    mode_str = "逐请求轮换" if mode.per_request else "固定当前"
    return SuccessResponse(success=True, message=f"轮换模式已设置为: {mode_str}")

@router.get("/status", response_model=SuccessResponse)
async def get_server_status():
    """获取服务器状态"""
    global server_instance
    if not server_instance or not server_instance._running:
        status = ServerStatus(
            http_running=False,
            http_port=0,
            socks5_running=False,
            socks5_port=0,
            current_proxy=None,
            rotation_mode="fixed"
        )
    else:
        status = ServerStatus(
            http_running=True,
            http_port=server_instance._http_port,
            socks5_running=True,
            socks5_port=server_instance._socks5_port,
            current_proxy=rotator_instance.get_current_proxy(),
            rotation_mode="per_request" if server_instance.rotate_per_request else "fixed"
        )
    
    return SuccessResponse(success=True, message="获取状态成功", data=status)
