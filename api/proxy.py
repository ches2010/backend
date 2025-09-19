from fastapi import APIRouter, BackgroundTasks
from typing import List
from ..schemas import *
from ..core.fetcher import ProxyFetcher
from ..core.checker import ProxyChecker
from ..core.rotator import ProxyRotator
import queue
import threading

router = APIRouter()

# 全局实例 (在实际生产中，应考虑使用依赖注入或单例模式)
rotator = ProxyRotator()
fetcher = ProxyFetcher()
checker = ProxyChecker()
log_queue = queue.Queue()

# 后台任务管理
background_tasks = set()

@router.post("/fetch", response_model=SuccessResponse)
async def fetch_proxies(request: FetchRequest, background_tasks: BackgroundTasks):
    """触发从在线源获取代理"""
    def _background_fetch():
        try:
            all_proxies = []
            for proto in ['http', 'socks4', 'socks5']:
                fetched = fetcher.fetch_all(log_queue, include_scraping=request.include_scraping)
                if fetched and proto in fetched:
                    all_proxies.extend([f"{p}#{proto}" for p in fetched[proto]]) # 暂时标记协议
            
            log_queue.put(f"[+] 总共获取到 {len(all_proxies)} 个原始代理，开始验证...")
            
            # 触发验证
            valid_proxies = checker.validate_proxies(all_proxies, log_queue, cancel_event=None)
            
            # 清空并添加到轮换器
            rotator.clear()
            for p_info in valid_proxies:
                rotator.add_proxy(p_info)
            
            log_queue.put(f"[+] 验证完成，成功添加 {len(valid_proxies)} 个高质量代理到池中。")
        except Exception as e:
            log_queue.put(f"[!] 获取和验证代理过程中出现错误: {str(e)}")

    background_tasks.add_task(_background_fetch)
    return SuccessResponse(success=True, message="代理获取任务已启动，请查看日志。")

@router.post("/check", response_model=SuccessResponse)
async def check_proxies(request: CheckRequest):
    """对指定的原始代理列表进行验证"""
    def _background_check():
        try:
            # 这里需要将原始字符串转换为 checker 能处理的格式
            # 假设输入是 ["ip:port#protocol", ...] 或者 ["ip:port"] (默认HTTP)
            raw_list = request.proxies
            valid_proxies = checker.validate_proxies(raw_list, log_queue, cancel_event=None)
            
            # 添加到轮换器 (可以选择是追加还是替换)
            for p_info in valid_proxies:
                rotator.add_proxy(p_info)
            
            log_queue.put(f"[+] 手动验证完成，成功添加 {len(valid_proxies)} 个代理。")
        except Exception as e:
            log_queue.put(f"[!] 验证代理过程中出现错误: {str(e)}")

    background_tasks.add_task(_background_check)
    return SuccessResponse(success=True, message="代理验证任务已启动，请查看日志。")

@router.get("/list", response_model=SuccessResponse)
async def get_proxy_list(filter_params: FilterParams = FilterParams()):
    """根据筛选条件获取代理列表"""
    # 设置轮换器的过滤器
    rotator.set_filters(
        region=filter_params.region,
        quality_latency_ms=filter_params.max_latency_ms
    )
    
    # 获取所有符合条件的代理 (这里为了列表展示，不按轮换顺序，而是全部返回)
    # 可以修改 ProxyRotator 以提供一个 get_filtered_proxies() 方法
    all_proxies = rotator.get_all_proxies_for_revalidation()
    filtered_list = []
    for p in all_proxies:
        if p.get('status') != 'Working':
            continue
        if filter_params.region != "All" and p.get('location') != filter_params.region:
            continue
        if filter_params.max_latency_ms is not None:
            if p.get('latency', float('inf')) * 1000 > filter_params.max_latency_ms:
                continue
        filtered_list.append(p)
    
    # 按分数排序
    filtered_list.sort(key=lambda x: x.get('score', 0), reverse=True)
    
    return SuccessResponse(success=True, message="获取成功", data=filtered_list)

@router.post("/rotate", response_model=SuccessResponse)
async def rotate_proxy():
    """手动轮换到下一个代理"""
    next_proxy = rotator.get_next_proxy()
    if next_proxy:
        message = f"已轮换到代理: {next_proxy['proxy']}"
    else:
        message = "无可用代理"
    return SuccessResponse(success=True, message=message, data=next_proxy)

@router.get("/regions", response_model=SuccessResponse)
async def get_available_regions(max_latency_ms: Optional[int] = None):
    """获取可用地区及其代理数量统计"""
    counts = rotator.get_available_regions_with_counts(quality_latency_ms=max_latency_ms)
    return SuccessResponse(success=True, message="获取成功", data=counts)

@router.get("/count", response_model=SuccessResponse)
async def get_active_proxy_count():
    """获取当前可用代理总数"""
    count = rotator.get_active_proxies_count()
    return SuccessResponse(success=True, message="获取成功", data={"count": count})

@router.get("/current", response_model=SuccessResponse)
async def get_current_proxy():
    """获取当前正在使用的代理"""
    current = rotator.get_current_proxy()
    return SuccessResponse(success=True, message="获取成功", data=current)

@router.delete("/proxy/{proxy_address}", response_model=SuccessResponse)
async def remove_proxy(proxy_address: str):
    """从池中移除指定代理"""
    success = rotator.remove_proxy(proxy_address)
    if success:
        message = f"代理 {proxy_address} 已移除。"
    else:
        message = f"未找到代理 {proxy_address}。"
    return SuccessResponse(success=success, message=message)

@router.get("/logs", response_model=SuccessResponse)
async def get_logs():
    """获取最新日志 (简化版，实际应用中建议用 WebSocket 或长轮询)"""
    logs = []
    while not log_queue.empty():
        try:
            log_entry = log_queue.get_nowait()
            logs.append(log_entry)
        except queue.Empty:
            break
    return SuccessResponse(success=True, message="获取日志", data=logs)
