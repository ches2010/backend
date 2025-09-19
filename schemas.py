from typing import List, Optional, Dict, Any
from pydantic import BaseModel

# --- 代理相关 ---
class ProxyInfo(BaseModel):
    proxy: str
    protocol: str
    latency: float
    speed: float
    anonymity: str
    location: str
    score: float
    status: str = "Working"
    consecutive_failures: int = 0

class FetchRequest(BaseModel):
    include_scraping: bool = True  # 是否包含爬虫源

class CheckRequest(BaseModel):
    proxies: List[str]  # 待验证的原始代理列表 ["ip:port", ...]

class FilterParams(BaseModel):
    region: str = "All"
    max_latency_ms: Optional[int] = None

class RotationMode(BaseModel):
    per_request: bool

# --- 服务器相关 ---
class ServerStatus(BaseModel):
    http_running: bool
    http_port: int
    socks5_running: bool
    socks5_port: int
    current_proxy: Optional[ProxyInfo]
    rotation_mode: str  # "fixed" or "per_request"

class StartServerRequest(BaseModel):
    http_port: int = 8080
    socks5_port: int = 1080

# --- 设置相关 ---
class GeneralSettings(BaseModel):
    check_threads: int
    failure_threshold: int
    auto_recheck: bool
    recheck_interval_minutes: int

class AssetSearchSettings(BaseModel):
    fofa_enabled: bool
    fofa_email: str
    fofa_key: str
    fofa_query: str
    fofa_size: int
    hunter_enabled: bool
    hunter_key: str
    hunter_query: str
    hunter_size: int
    quake_enabled: bool
    quake_key: str
    quake_query: str
    quake_size: int

class Settings(BaseModel):
    general: GeneralSettings
    asset_search: AssetSearchSettings

# --- 通用响应 ---
class SuccessResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Any] = None

class ErrorResponse(BaseModel):
    success: bool = False
    message: str
