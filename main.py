# main.py

import argparse
import json
import os
import sys
import threading
from queue import Queue, Empty
import time

# 添加 modules 目录到 Python 路径，以便导入 proxy_manager
sys.path.append(os.path.join(os.path.dirname(__file__), 'modules'))

from proxy_manager import ProxyManager
import hq # 导入 hq 模块

# 默认配置
DEFAULT_CONFIG_PATH = 'config.json'
DEFAULT_LOG_INTERVAL = 1.0 # 秒

def load_config(config_path):
    """加载配置文件"""
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    else:
        print(f"[警告] 配置文件 {config_path} 不存在，使用默认配置。")
        return {}

def run_proxy_service(config, log_queue):
    """运行本地代理服务"""
    pm = ProxyManager(timeout=config.get('validation', {}).get('timeout', 5))
    pm.set_log_queue(log_queue)
    
    # 初始刷新一次代理
    print("[*] 初始刷新代理...")
    pm.refresh_proxies(log_queue)
    
    # 启动服务
    http_config = config.get('proxy_server', {}).get('http', {})
    socks5_config = config.get('proxy_server', {}).get('socks5', {})
    auto_refresh = config.get('proxy_server', {}).get('auto_refresh_minutes', 0)
    
    pm.start_local_proxy_service(
        http_host=http_config.get('host', '127.0.0.1'),
        http_port=http_config.get('port', 8888),
        socks5_host=socks5_config.get('host', '127.0.0.1'),
        socks5_port=socks5_config.get('port', 1080),
        auto_refresh_minutes=auto_refresh
    )
    print("[*] 本地代理服务已启动。")
    print(f"    HTTP 代理: {http_config.get('host', '127.0.0.1')}:{http_config.get('port', 8888)}")
    print(f"    SOCKS5 代理: {socks5_config.get('host', '127.0.0.1')}:{socks5_config.get('port', 1080)}")
    if auto_refresh > 0:
        print(f"    自动刷新: 每 {auto_refresh} 分钟")
    else:
        print("    自动刷新: 已禁用")
    print("[*] 按 Ctrl+C 停止服务。")
    try:
        # 保持主线程运行
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] 正在停止服务...")
        pm.stop_local_proxy_service()
        print("[*] 服务已停止。")

def run_cli_refresh(config, log_queue):
    """运行CLI刷新代理"""
    pm = ProxyManager(timeout=config.get('validation', {}).get('timeout', 5))
    pm.set_log_queue(log_queue)
    print("[*] 开始刷新代理...")
    count = pm.refresh_proxies(log_queue)
    print(f"[+] 完成，共获取并验证 {count} 个可用代理。")

def run_hq_fetch(log_queue, output_dir):
    """运行hq.py获取代理"""
    print("[*] 开始通过 hq.py 获取代理...")
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    # 简单地将 hq 的 print 重定向到日志队列
    class LogRedirect:
        def __init__(self, queue):
            self.queue = queue
        def write(self, buf):
            for line in buf.rstrip().splitlines():
                self.queue.put(f"[hq] {line}")
        def flush(self):
            pass
    
    sys.stdout = LogRedirect(log_queue)
    sys.stderr = LogRedirect(log_queue)
    
    try:
        hq.fetch_and_save_proxies(output_dir=output_dir)
        log_queue.put("[+] hq.py 获取代理完成。")
    except Exception as e:
        log_queue.put(f"[!] hq.py 执行出错: {e}")
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr

def log_consumer(log_queue, stop_event, interval=DEFAULT_LOG_INTERVAL):
    """从队列消费日志并打印"""
    while not stop_event.is_set():
        try:
            # 使用 timeout 避免无限期阻塞，以便能响应 stop_event
            message = log_queue.get(timeout=interval)
            print(message)
        except Empty:
            continue # 队列为空，继续检查 stop_event

def main():
    parser = argparse.ArgumentParser(description="全能代理管理器")
    parser.add_argument('--config', type=str, default=DEFAULT_CONFIG_PATH, help='配置文件路径')
    parser.add_argument('--mode', choices=['service', 'refresh', 'hq'], default='service', help='运行模式: service (启动代理服务), refresh (CLI刷新), hq (运行hq.py)')
    parser.add_argument('--output-dir', type=str, help='hq模式下指定输出目录')
    parser.add_argument('--log-interval', type=float, default=DEFAULT_LOG_INTERVAL, help='日志打印间隔 (秒)')
    
    args = parser.parse_args()
    
    config = load_config(args.config)
    
    # 创建一个队列用于接收日志
    log_queue = Queue()
    stop_event = threading.Event()
    
    # 启动日志消费者线程
    log_thread = threading.Thread(target=log_consumer, args=(log_queue, stop_event, args.log_interval), daemon=True)
    log_thread.start()
    
    try:
        if args.mode == 'service':
            run_proxy_service(config, log_queue)
        elif args.mode == 'refresh':
            run_cli_refresh(config, log_queue)
        elif args.mode == 'hq':
            output_dir = args.output_dir if args.output_dir else os.getcwd()
            run_hq_fetch(log_queue, output_dir)
    finally:
        # 请求停止日志线程
        stop_event.set()
        # 等待日志线程处理完队列中剩余的消息
        log_thread.join(timeout=2) 
        print("[*] 程序退出。")

if __name__ == '__main__':
    main()
