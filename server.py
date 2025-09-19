# modules/server.py (整合 AssetSearcher 功能后)

import socket
import threading
import select
import struct
import socks
import time
from urllib.parse import urlparse
from modules.asset_searcher import AssetSearcher  # <-- 新增导入

class ProxyServer:
    """本地代理服务，支持自动从网络空间引擎获取代理并轮换使用。"""

    def __init__(self, http_host, http_port, socks5_host, socks5_port, rotator, log_queue, auto_refresh_minutes=0):
        self._rotator = rotator
        self._log_queue = log_queue
        self._running = False
        self._http_host = http_host
        self._http_port = http_port
        self._http_server_socket = None
        self._http_thread = None
        self._socks5_host = socks5_host
        self._socks5_port = socks5_port
        self._socks5_server_socket = None
        self._socks5_thread = None
        self.rotate_per_request = False
        
        # --- NEW: 集成 AssetSearcher ---
        self._searcher = AssetSearcher(log_queue)
        self._auto_refresh_minutes = auto_refresh_minutes
        self._refresh_thread = None

    def log(self, message):
        self._log_queue.put(f"[Server] {message}")

    def set_rotation_mode(self, per_request: bool):
        self.rotate_per_request = per_request
        mode = "逐请求轮换" if per_request else "固定当前"
        self.log(f"服务轮换模式已切换为: {mode}")

    def start_all(self):
        if self._running:
            return
        self._running = True

        # 启动代理服务线程
        self._http_thread = threading.Thread(target=self._run_http_server, daemon=True)
        self._http_thread.start()
        self._socks5_thread = threading.Thread(target=self._run_socks5_server, daemon=True)
        self._socks5_thread.start()

        # 启动自动刷新线程（如果设置了刷新间隔）
        if self._auto_refresh_minutes > 0:
            self._refresh_thread = threading.Thread(target=self._auto_refresh_proxies, daemon=True)
            self._refresh_thread.start()
            self.log(f"代理自动刷新已启用，每 {self._auto_refresh_minutes} 分钟执行一次。")

    def stop_all(self):
        if not self._running:
            return
        self._running = False

        if self._http_server_socket:
            self._http_server_socket.close()
        if self._socks5_server_socket:
            self._socks5_server_socket.close()
        if self._http_thread and self._http_thread.is_alive():
            self._http_thread.join()
        if self._socks5_thread and self._socks5_thread.is_alive():
            self._socks5_thread.join()
        if self._refresh_thread and self._refresh_thread.is_alive():
            self._refresh_thread.join()

        self.log("所有代理服务已停止。")

    # --- NEW: 获取并加载代理到轮换器 ---
    def fetch_and_load_proxies(self, fetch_settings):
        """从搜索引擎获取代理，并更新到轮换器"""
        self.log("[🔄] 正在从网络空间引擎获取最新代理列表...")
        proxies = self._searcher.search_all(fetch_settings)
        
        if not proxies:
            self.log("[⚠️] 未获取到任何代理，请检查配置或API Key。")
            return False

        # 假设轮换器提供 update_proxies(list) 方法
        # 格式化为 [{'proxy': 'ip:port', 'protocol': 'SOCKS5'}, ...]
        proxy_list = [{'proxy': p, 'protocol': 'SOCKS5'} for p in proxies]
        self._rotator.update_proxies(proxy_list)
        self.log(f"[✅] 成功加载 {len(proxies)} 个代理到轮换池。")
        return True

    # --- NEW: 自动刷新代理 ---
    def _auto_refresh_proxies(self):
        while self._running:
            try:
                # 这里应从外部传入 fetch_settings，这里简化写死或从配置读取
                # 实际项目中建议保存 fetch_settings 到实例变量
                # 示例：
                # if hasattr(self, '_last_fetch_settings'):
                #     self.fetch_and_load_proxies(self._last_fetch_settings)
                
                # 为演示，我们假设默认配置存在
                default_settings = {
                    "fofa": {"enabled": True, "key": "your_email:your_key", "query": 'protocol="socks5"', "size": 50},
                    "quake": {"enabled": True, "key": "your_quake_key", "query": 'service:"socks5"', "size": 50},
                    "hunter": {"enabled": True, "key": "your_hunter_key", "query": '"socks5"', "size": 50}
                }
                self.fetch_and_load_proxies(default_settings)
            except Exception as e:
                self.log(f"[❌] 自动刷新代理失败: {e}")
            
            # 等待指定分钟
            for _ in range(self._auto_refresh_minutes * 60):
                if not self._running:
                    break
                time.sleep(1)

    # ========== 以下为原有代码，保持不变 ==========

    def _run_http_server(self):
        try:
            self._http_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._http_server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._http_server_socket.bind((self._http_host, self._http_port))
            self._http_server_socket.listen(20)
            self.log(f"HTTP 代理服务接口已启动于 {self._http_host}:{self._http_port}")
        except Exception as e:
            self.log(f"[!] 启动 HTTP 服务失败: {e}")
            return
        while self._running:
            try:
                client_socket, _ = self._http_server_socket.accept()
                handler = threading.Thread(target=self._handle_http_client, args=(client_socket,), daemon=True)
                handler.start()
            except OSError:
                break 
        self.log("HTTP 代理服务循环已退出。")

    def _run_socks5_server(self):
        try:
            self._socks5_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socks5_server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._socks5_server_socket.bind((self._socks5_host, self._socks5_port))
            self._socks5_server_socket.listen(20)
            self.log(f"SOCKS5 代理服务接口已启动于 {self._socks5_host}:{self._socks5_port}")
        except Exception as e:
            self.log(f"[!] 启动 SOCKS5 服务失败: {e}")
            return
        while self._running:
            try:
                client_socket, _ = self._socks5_server_socket.accept()
                handler = threading.Thread(target=self._handle_socks5_client, args=(client_socket,), daemon=True)
                handler.start()
            except OSError:
                break
        self.log("SOCKS5 代理服务循环已退出。")
        
    def _get_upstream_connection(self, target_host, target_port):
        if self.rotate_per_request:
            upstream_proxy_info = self._rotator.get_next_proxy()
        else:
            upstream_proxy_info = self._rotator.get_current_proxy()
        if not upstream_proxy_info:
            self.log("[!] 代理池为空或无符合条件的代理，无法转发请求。")
            return None
        addr = upstream_proxy_info.get('proxy')
        proto = upstream_proxy_info.get('protocol')
        if not addr or not proto:
            self.log(f"[!] 代理信息格式不正确: {upstream_proxy_info}")
            return None
        upstream_addr, upstream_port_str = addr.split(':')
        
        proxy_type_map = {'HTTP': socks.HTTP, 'SOCKS4': socks.SOCKS4, 'SOCKS5': socks.SOCKS5}
        upstream_protocol = proxy_type_map.get(proto.upper())
        if not upstream_protocol:
            self.log(f"[!] 不支持的上游代理协议: {proto}")
            return None
        
        remote_socket = socks.socksocket()
        try:
            remote_socket.set_proxy(proxy_type=upstream_protocol, addr=upstream_addr, port=int(upstream_port_str))
            remote_socket.connect((target_host, target_port))
            if self.rotate_per_request:
                self.log(f"轮换: {addr} -> {target_host}:{target_port}")
            return remote_socket
        except Exception as e:
            self.log(f"[!] 上游代理 {addr} 错误: {e}")
            remote_socket.close()
            return None

    def _handle_http_client(self, client_socket):
        remote_socket = None
        try:
            request_data = client_socket.recv(8192)
            if not request_data:
                return
            first_line = request_data.split(b'\r\n')[0].decode('utf-8', 'ignore')
            method, url, _ = first_line.split()
            if method == 'CONNECT':
                target_host, target_port_str = url.split(':')
                target_port = int(target_port_str)
            else:
                parsed_url = urlparse(url)
                target_host = parsed_url.hostname
                target_port = parsed_url.port or 80
            remote_socket = self._get_upstream_connection(target_host, target_port)
            if not remote_socket:
                client_socket.sendall(b'HTTP/1.1 502 Bad Gateway\r\n\r\n')
                return
            if method == 'CONNECT':
                client_socket.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')
            else:
                remote_socket.sendall(request_data)
            self._forward_data(client_socket, remote_socket)
        except Exception as e:
            if not isinstance(e, (ConnectionResetError, BrokenPipeError, OSError)):
                 self.log(f"处理 HTTP 请求时出错: {e}")
        finally:
            if remote_socket: remote_socket.close()
            if client_socket: client_socket.close()

    def _handle_socks5_client(self, client_socket):
        remote_socket = None
        try:
            data = client_socket.recv(2)
            if not data or data[0] != 5: return 
            nmethods = data[1]
            client_socket.recv(nmethods)
            client_socket.sendall(b"\x05\x00")
            data = client_socket.recv(4)
            if not data or data[0] != 5 or data[1] != 1: return
            
            atyp = data[3]
            if atyp == 1:
                addr = socket.inet_ntoa(client_socket.recv(4))
            elif atyp == 3:
                domain_len = client_socket.recv(1)[0]
                addr = client_socket.recv(domain_len).decode('utf-8')
            else:
                client_socket.sendall(b"\x05\x08\x00\x01\x00\x00\x00\x00\x00\x00")
                return
            
            port = struct.unpack('!H', client_socket.recv(2))[0]
            remote_socket = self._get_upstream_connection(addr, port)
            if not remote_socket:
                client_socket.sendall(b"\x05\x04\x00\x01\x00\x00\x00\x00\x00\x00")
                return
            client_socket.sendall(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
            self._forward_data(client_socket, remote_socket)
        except Exception as e:
            if not isinstance(e, (ConnectionResetError, BrokenPipeError, OSError)):
                self.log(f"处理 SOCKS5 请求时出错: {e}")
        finally:
            if remote_socket: remote_socket.close()
            if client_socket: client_socket.close()

    def _forward_data(self, sock1, sock2):
        while self._running:
            try:
                readable, _, exceptional = select.select([sock1, sock2], [], [sock1, sock2], 5)
                if exceptional or not readable:
                    break
                for sock in readable:
                    other_sock = sock2 if sock is sock1 else sock1
                    data = sock.recv(8192)
                    if not data:
                        return
                    other_sock.sendall(data)
            except (ConnectionResetError, BrokenPipeError, OSError, select.error):
                break
