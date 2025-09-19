# modules/proxy_manager.py (增强全能版 - 修复版)

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
from bs4 import BeautifulSoup
import json
import time
import threading
from collections import defaultdict
import socket
import subprocess
import select
import socks
from urllib.parse import urlparse
import struct

class ProxyManager:
    """全能代理管理器，负责获取、验证、管理、轮换和筛选代理。"""

    def __init__(self, timeout: int = 5):
        """初始化，定义API源、爬虫源、验证目标，并设置管理器内部状态。"""
        # --- 初始化 Fetcher 部分 ---
        # API源 (主要为返回纯文本格式的URL)
        self.online_sources = {
            'http': [
                # 经典源
                'https://api.proxyscrape.com/v3/free-proxy-list/get?request=displayproxies&protocol=http',
                'https://openproxylist.xyz/http.txt',
                'https://www.proxy-list.download/api/v1/get?type=http',
                'https://proxylist.geonode.com/api/proxy-list?limit=500&page=1&sort_by=lastChecked&sort_type=desc&protocols=http',
                'https://www.proxyscan.io/api/proxy?type=http&format=txt',
                # 您提供的新源
                'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt',
                'http://77.93.157.21:3030/fetch_all',
                'http://199.245.100.84:5000/fetch_all',
                'http://123.117.160.38:5000/fetch_all',
                'http://142.171.31.40:5010/fetch_all',
                'http://120.46.21.7:5000/fetch_all',
            ],
            'https': [
                 'https://www.proxy-list.download/api/v1/get?type=https',
            ],
            'socks4': [
                'https://api.proxyscrape.com/v3/free-proxy-list/get?request=displayproxies&protocol=socks4',
                'https://openproxylist.xyz/socks4.txt',
                'https://www.proxy-list.download/api/v1/get?type=socks4',
            ],
            'socks5': [
                'https://api.proxyscrape.com/v3/free-proxy-list/get?request=displayproxies&protocol=socks5',
                'https://openproxylist.xyz/socks5.txt',
                'https://www.proxy-list.download/api/v1/get?type=socks5',
                'https://www.proxyscan.io/api/proxy?type=socks5&format=txt',
            ]
        }
        
        # 爬虫源 (需要解析HTML页面的网站)
        self.scraping_sources = [
            {'func': self._scrape_free_proxy_list, 'protocol': 'http'},
            {'func': self._scrape_kxdaili, 'protocol': 'http'},
            {'func': self._scrape_66ip, 'protocol': 'http'},
            {'func': self._scrape_fatezero, 'protocol': 'http'},
            # 新增的国内代理源
            {'func': self._scrape_kuaidaili, 'protocol': 'http'},
            {'func': self._scrape_ip3366, 'protocol': 'http'},
            {'func': self._scrape_89ip, 'protocol': 'http'},
        ]
        self.fetcher_session = self._create_robust_session()

        # --- 初始化 Checker 部分 ---
        self.timeout = timeout
        self.checker_session = requests.Session()
        self.checker_session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
        })
        
        self.validation_targets = {
            'latency_check': 'https://www.baidu.com',
            'anonymity_check': 'http://httpbin.org/get?show_env=1',
            'speed_check': 'http://cachefly.cachefly.net/100kb.test',
        }
        
        # 国家名称中文映射
        self.COUNTRY_NAME_MAP = {
            'China': '中国',
            'Hong Kong': '香港',
            'Singapore': '新加坡',
            'United States': '美国',
            'Japan': '日本',
            'South Korea': '韩国',
            'Russia': '俄罗斯',
            'Germany': '德国',
            'United Kingdom': '英国',
            'France': '法国',
            'Canada': '加拿大',
            'Taiwan': '台湾',
            'Netherlands': '荷兰',
            'India': '印度',
            'Vietnam': '越南',
            'Thailand': '泰国',
        }
        self.location_cache = {}
        self.public_ip = None

        # --- 初始化 Rotator 部分 ---
        self.all_proxies = []
        self.proxies_by_country = defaultdict(list)
        self.indices = defaultdict(lambda: -1)
        self.current_proxy = None
        self.lock = threading.Lock()
        self.current_filter_region = "All"
        self.current_filter_quality_latency_ms = None

        # --- 初始化 Logger ---
        self.log_queue = None  # 外部传入或默认队列

        # --- 初始化 AssetSearcher (内嵌简化版) ---
        self._searcher = None  # 初始化时创建

        # --- 初始化 ProxyServer (内嵌) ---
        self._proxy_server = None
        self._auto_refresh_minutes = 0
        self._refresh_thread = None


    # ========== AssetSearcher 内嵌实现 ==========
    class AssetSearcher:
        def __init__(self, log_queue):
            self.log_queue = log_queue
            self.engines = {
                'fofa': self._search_fofa,
                'quake': self._search_quake,
                'hunter': self._search_hunter
            }

        def log(self, msg):
            if self.log_queue:
                self.log_queue.put(f"[AssetSearcher] {msg}")

        def _search_fofa(self, key, query, size, page=1):
            email, fofa_key = key.split(':', 1)
            url = f"https://fofa.info/api/v1/search/all?email={email}&key={fofa_key}&qbase64={query.encode().hex()}&size={size}&page={page}&fields=host,port"
            try:
                res = requests.get(url, timeout=10)
                res.raise_for_status()
                data = res.json()
                return [f"{item[0]}:{item[1]}" for item in data.get('results', [])]
            except Exception as e:
                self.log(f"FOFA 搜索失败: {e}")
                return []

        def _search_quake(self, key, query, size):
            url = "https://quake.360.cn/api/v3/search/quake_service"
            headers = {'X-QuakeToken': key}
            data = {"query": query, "size": size, "ignore_cache": False}
            try:
                res = requests.post(url, json=data, headers=headers, timeout=10)
                res.raise_for_status()
                results = res.json().get('data', [])
                return [f"{r['ip']}:{r['port']}" for r in results]
            except Exception as e:
                self.log(f"Quake 搜索失败: {e}")
                return []

        def _search_hunter(self, key, query, size, start=1):
            url = f"https://hunter.qianxin.com/openApi/search?api-key={key}&search={query}&page={start}&page_size={size}&is_web=3"
            try:
                res = requests.get(url, timeout=10)
                res.raise_for_status()
                data = res.json()
                return [f"{item['ip']}:{item['port']}" for item in data.get('data', {}).get('arr', [])]
            except Exception as e:
                self.log(f"Hunter 搜索失败: {e}")
                return []

        def search_all(self, settings):
            all_proxies = set()
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = []
                for engine_name, config in settings.items():
                    if not config.get('enabled', False):
                        continue
                    func = self.engines.get(engine_name)
                    if not func:
                        continue
                    future = executor.submit(
                        func,
                        config['key'],
                        config['query'],
                        config.get('size', 50)
                    )
                    futures.append(future)

                for future in as_completed(futures):
                    try:
                        proxies = future.result()
                        all_proxies.update(proxies)
                    except Exception as e:
                        self.log(f"引擎搜索异常: {e}")

            return list(all_proxies)


    # ========== ProxyServer 内嵌实现 ==========
    class ProxyServer:
        def __init__(self, manager, http_host, http_port, socks5_host, socks5_port, log_queue):
            self.manager = manager
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
            self._http_thread = threading.Thread(target=self._run_http_server, daemon=True)
            self._http_thread.start()
            self._socks5_thread = threading.Thread(target=self._run_socks5_server, daemon=True)
            self._socks5_thread.start()
            self.log(f"HTTP 服务启动于 {self._http_host}:{self._http_port}")
            self.log(f"SOCKS5 服务启动于 {self._socks5_host}:{self._socks5_port}")

        def stop_all(self):
            if not self._running:
                return
            self._running = False
            for sock in [self._http_server_socket, self._socks5_server_socket]:
                if sock: sock.close()
            for t in [self._http_thread, self._socks5_thread]:
                if t and t.is_alive(): t.join()
            self.log("所有代理服务已停止。")

        def _get_upstream_connection(self, target_host, target_port):
            if self.rotate_per_request:
                proxy_info = self.manager.get_next_proxy()
            else:
                proxy_info = self.manager.get_current_proxy()
            if not proxy_info:
                self.log("[!] 代理池为空")
                return None
            addr = proxy_info.get('proxy')
            proto = proxy_info.get('protocol', 'SOCKS5')
            if not addr:
                return None
            upstream_addr, upstream_port_str = addr.split(':')
            proxy_type_map = {'HTTP': socks.HTTP, 'SOCKS4': socks.SOCKS4, 'SOCKS5': socks.SOCKS5}
            upstream_protocol = proxy_type_map.get(proto.upper())
            if not upstream_protocol:
                self.log(f"[!] 不支持协议: {proto}")
                return None
            remote_socket = socks.socksocket()
            try:
                remote_socket.set_proxy(proxy_type=upstream_protocol, addr=upstream_addr, port=int(upstream_port_str))
                remote_socket.connect((target_host, target_port))
                return remote_socket
            except Exception as e:
                self.log(f"[!] 代理 {addr} 连接失败: {e}")
                remote_socket.close()
                return None

        def _forward_data(self, sock1, sock2):
            while self._running:
                try:
                    readable, _, exceptional = select.select([sock1, sock2], [], [sock1, sock2], 5)
                    if exceptional or not readable: break
                    for sock in readable:
                        other = sock2 if sock is sock1 else sock1
                        data = sock.recv(8192)
                        if not data: return
                        other.sendall(data)
                except: break

        def _handle_http_client(self, client_socket):
            remote_socket = None
            try:
                data = client_socket.recv(8192)
                if not data: return
                first_line = data.split(b'\r\n')[0].decode('utf-8', 'ignore')
                method, url, _ = first_line.split()
                if method == 'CONNECT':
                    host, port_str = url.split(':')
                    port = int(port_str)
                else:
                    parsed = urlparse(url)
                    host = parsed.hostname
                    port = parsed.port or 80
                remote_socket = self._get_upstream_connection(host, port)
                if not remote_socket:
                    client_socket.sendall(b'HTTP/1.1 502 Bad Gateway\r\n\r\n')
                    return
                if method == 'CONNECT':
                    client_socket.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')
                else:
                    remote_socket.sendall(data)
                self._forward_data(client_socket, remote_socket)
            except Exception as e:
                if not isinstance(e, (ConnectionResetError, BrokenPipeError, OSError)):
                    self.log(f"HTTP处理异常: {e}")
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
                    self.log(f"SOCKS5处理异常: {e}")
            finally:
                if remote_socket: remote_socket.close()
                if client_socket: client_socket.close()

        def _run_http_server(self):
            try:
                self._http_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._http_server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self._http_server_socket.bind((self._http_host, self._http_port))
                self._http_server_socket.listen(20)
            except Exception as e:
                self.log(f"[!] HTTP启动失败: {e}")
                return
            while self._running:
                try:
                    client, _ = self._http_server_socket.accept()
                    threading.Thread(target=self._handle_http_client, args=(client,), daemon=True).start()
                except OSError: break

        def _run_socks5_server(self):
            try:
                self._socks5_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._socks5_server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self._socks5_server_socket.bind((self._socks5_host, self._socks5_port))
                self._socks5_server_socket.listen(20)
            except Exception as e:
                self.log(f"[!] SOCKS5启动失败: {e}")
                return
            while self._running:
                try:
                    client, _ = self._socks5_server_socket.accept()
                    threading.Thread(target=self._handle_socks5_client, args=(client,), daemon=True).start()
                except OSError: break
        
        # 保存当前激活的过滤器状态
        self.current_filter_region = "All"
        self.current_filter_quality_latency_ms = None

    def _create_robust_session(self):
        """为Fetcher创建一个健壮的requests会话。"""
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
            "Referer": "https://www.google.com/"
        })
        retry_strategy = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    # --- Fetcher 核心方法 ---
    def _parse_proxies_from_text(self, text: str):
        """从文本或JSON中解析出代理列表。"""
        try:
            data = json.loads(text)
            if 'data' in data and isinstance(data['data'], list):
                return [f"{item['ip']}:{item['port']}" for item in data['data']]
        except json.JSONDecodeError:
            pass
        
        return [line.strip() for line in text.splitlines() if re.match(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{1,3}', line.strip())]

    def _fetch_from_url(self, url: str, log_queue):
        """从指定URL获取代理列表。"""
        display_url = url.split('/')[2]
        log_queue.put(f"[*] (API) 正在从 {display_url} 获取...")
        try:
            response = self.fetcher_session.get(url, timeout=15)
            response.raise_for_status()
            proxies = self._parse_proxies_from_text(response.text)
            if proxies:
                log_queue.put(f"[+] (API) 成功从 {display_url} 获取 {len(proxies)} 个代理。")
                return proxies
            else:
                log_queue.put(f"[-] (API) 从 {display_url} 获取为空。")
                return None
        except requests.RequestException as e:
            log_queue.put(f"[!] (API) 从 {display_url} 获取失败: {e}")
            return None

    def _scrape_free_proxy_list(self, log_queue):
        """爬取 free-proxy-list.net 的代理。"""
        url = 'https://free-proxy-list.net/'
        display_url = url.split('/')[2]
        log_queue.put(f"[*] (Scrape) 正在从 {display_url} 获取...")
        try:
            response = self.fetcher_session.get(url, timeout=15)
            soup = BeautifulSoup(response.content, 'lxml')
            proxies = set()
            table = soup.find('table', class_='table-striped')
            for row in table.find_all('tr')[1:]:
                cols = row.find_all('td')
                if len(cols) > 6 and cols[6].text.strip() == 'yes':
                    ip = cols[0].text.strip()
                    port = cols[1].text.strip()
                    proxies.add(f"{ip}:{port}")
            log_queue.put(f"[+] (Scrape) 成功从 {display_url} 获取 {len(proxies)} 个代理。")
            return list(proxies)
        except Exception as e:
            log_queue.put(f"[!] (Scrape) 从 {display_url} 获取失败: {e}")
            return None

    def _scrape_kxdaili(self, log_queue):
        """爬取 kxdaili.com 的代理。"""
        url = 'http://www.kxdaili.com/dailiip/1/1.html'
        display_url = url.split('/')[2]
        log_queue.put(f"[*] (Scrape) 正在从 {display_url} 获取...")
        try:
            response = self.fetcher_session.get(url, timeout=15)
            response.encoding = 'gb2312'
            soup = BeautifulSoup(response.content, 'lxml')
            proxies = set()
            table = soup.find('table', class_='active')
            for row in table.find_all('tr')[1:]:
                cols = row.find_all('td')
                if len(cols) > 3 and 'HTTPS' in cols[3].text.upper():
                    ip = cols[0].text.strip()
                    port = cols[1].text.strip()
                    proxies.add(f"{ip}:{port}")
            log_queue.put(f"[+] (Scrape) 成功从 {display_url} 获取 {len(proxies)} 个代理。")
            return list(proxies)
        except Exception as e:
            log_queue.put(f"[!] (Scrape) 从 {display_url} 获取失败: {e}")
            return None
            
    def _scrape_66ip(self, log_queue):
        """爬取 66ip.cn 的代理。"""
        url = "http://www.66ip.cn/nmtq.php?get_num=300&isp=0&type=2"
        display_url = url.split('/')[2]
        log_queue.put(f"[*] (API) 正在从 {display_url} 获取...")
        try:
            response = self.fetcher_session.get(url, timeout=15)
            response.encoding = response.apparent_encoding
            proxies = re.findall(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{2,5}', response.text)
            if proxies:
                log_queue.put(f"[+] (API) 成功从 {display_url} 获取 {len(proxies)} 个代理。")
                return proxies
            else:
                log_queue.put(f"[-] (API) 从 {display_url} 获取为空。")
                return None
        except Exception as e:
            log_queue.put(f"[!] (API) 从 {display_url} 获取失败: {e}")
            return None

    def _scrape_fatezero(self, log_queue):
        """爬取 fatezero.org 的代理。"""
        url = "http://proxylist.fatezero.org/proxy.list"
        display_url = url.split('/')[2]
        log_queue.put(f"[*] (Scrape) 正在从 {display_url} 获取...")
        try:
            response = self.fetcher_session.get(url, timeout=15)
            response.raise_for_status()
            proxies = set()
            for line in response.text.split('\n'):
                if 'host' in line:
                    proxy_info = json.loads(line)
                    if proxy_info.get('type') in ('http', 'https'):
                         host = proxy_info.get('host')
                         port = proxy_info.get('port')
                         proxies.add(f"{host}:{port}")
            if proxies:
                log_queue.put(f"[+] (Scrape) 成功从 {display_url} 获取 {len(proxies)} 个代理。")
                return list(proxies)
            else:
                 log_queue.put(f"[-] (Scrape) 从 {display_url} 获取为空。")
                 return None
        except Exception as e:
            log_queue.put(f"[!] (Scrape) 从 {display_url} 获取失败: {e}")
            return None

    def _scrape_kuaidaili(self, log_queue):
        """爬取快代理网站的国内高匿代理。"""
        proxies = set()
        display_url = "kuaidaili.com"
        log_queue.put(f"[*] (Scrape) 正在从 {display_url} 获取...")
        try:
            for page in range(1, 4):  # 爬取前3页
                url = f"https://www.kuaidaili.com/free/inha/{page}/"
                response = self.fetcher_session.get(url, timeout=15)
                response.raise_for_status()
                soup = BeautifulSoup(response.content, 'lxml')
                table = soup.find('table')
                if not table: continue
                for row in table.find('tbody').find_all('tr'):
                    cols = row.find_all('td')
                    if len(cols) > 1:
                        ip = cols[0].text.strip()
                        port = cols[1].text.strip()
                        proxies.add(f"{ip}:{port}")
                time.sleep(1) # 友好爬取，避免被封
            
            if proxies:
                log_queue.put(f"[+] (Scrape) 成功从 {display_url} 获取 {len(proxies)} 个代理。")
                return list(proxies)
            return None
        except Exception as e:
            log_queue.put(f"[!] (Scrape) 从 {display_url} 获取失败: {e}")
            return None

    def _scrape_ip3366(self, log_queue):
        """爬取云代理(ip3366.net)的国内高匿代理。"""
        proxies = set()
        display_url = "ip3366.net"
        log_queue.put(f"[*] (Scrape) 正在从 {display_url} 获取...")
        try:
            for page in range(1, 4): # 爬取前3页
                url = f"http://www.ip3366.net/free/?stype=1&page={page}"
                response = self.fetcher_session.get(url, timeout=15)
                response.encoding = 'gb2312'
                response.raise_for_status()
                soup = BeautifulSoup(response.content, 'lxml')
                table = soup.find('table', id='list')
                if not table: continue
                for row in table.find('tbody').find_all('tr'):
                    cols = row.find_all('td')
                    if len(cols) > 1:
                        ip = cols[0].text.strip()
                        port = cols[1].text.strip()
                        proxies.add(f"{ip}:{port}")
                time.sleep(1)
            
            if proxies:
                log_queue.put(f"[+] (Scrape) 成功从 {display_url} 获取 {len(proxies)} 个代理。")
                return list(proxies)
            return None
        except Exception as e:
            log_queue.put(f"[!] (Scrape) 从 {display_url} 获取失败: {e}")
            return None

    def _scrape_89ip(self, log_queue):
        """爬取89免费代理(89ip.cn)的代理。"""
        proxies = set()
        display_url = "89ip.cn"
        log_queue.put(f"[*] (Scrape) 正在从 {display_url} 获取...")
        try:
            for page in range(1, 4): # 爬取前3页
                url = f"https://www.89ip.cn/index_{page}.html"
                response = self.fetcher_session.get(url, timeout=15)
                response.raise_for_status()
                soup = BeautifulSoup(response.content, 'lxml')
                table = soup.find('table', class_='layui-table')
                if not table: continue
                for row in table.find('tbody').find_all('tr'):
                    cols = row.find_all('td')
                    if len(cols) > 1:
                        ip = cols[0].text.strip()
                        port = cols[1].text.strip()
                        proxies.add(f"{ip}:{port}")
                time.sleep(1)
            
            if proxies:
                log_queue.put(f"[+] (Scrape) 成功从 {display_url} 获取 {len(proxies)} 个代理。")
                return list(proxies)
            return None
        except Exception as e:
            log_queue.put(f"[!] (Scrape) 从 {display_url} 获取失败: {e}")
            return None

    def fetch_all_proxies(self, log_queue, cancel_event=None):
        """
        从所有在线和爬虫源获取代理。
        返回一个字典，包含'http', 'socks4', 'socks5'类型的代理列表。
        """
        all_proxies = {'http': set(), 'https': set(), 'socks4': set(), 'socks5': set()}
        
        executor = ThreadPoolExecutor(max_workers=50)
        try:
            future_to_protocol = {}
            # 提交API源任务
            for protocol, urls in self.online_sources.items():
                for url in urls:
                    if cancel_event and cancel_event.is_set(): break
                    future = executor.submit(self._fetch_from_url, url, log_queue)
                    future_to_protocol[future] = protocol
                if cancel_event and cancel_event.is_set(): break
            
            # 提交爬虫源任务
            if not (cancel_event and cancel_event.is_set()):
                for source in self.scraping_sources:
                    if cancel_event and cancel_event.is_set(): break
                    future = executor.submit(source['func'], log_queue)
                    future_to_protocol[future] = source['protocol']
            # 处理已完成的future
            for future in as_completed(future_to_protocol):
                if cancel_event and cancel_event.is_set():
                    break
                protocol = future_to_protocol[future]
                try:
                    proxies = future.result()
                    if proxies:
                        if protocol == 'https':
                            all_proxies['http'].update(proxies)
                        else:
                            all_proxies[protocol].update(proxies)
                except Exception as exc:
                    log_queue.put(f'[!] 获取器线程产生一个错误: {exc}')
        finally:
            executor.shutdown(wait=not (cancel_event and cancel_event.is_set()))
        if 'https' in all_proxies:
            del all_proxies['https']
            
        return {
            'http': list(all_proxies.get('http', set())),
            'socks4': list(all_proxies.get('socks4', set())),
            'socks5': list(all_proxies.get('socks5', set()))
        }

    # --- Checker 核心方法 ---
    def initialize_public_ip(self, log_queue=None):
        """通过调用系统 'curl' 命令获取本机公网IP，作为匿名度检测的基准。"""
        try:
            command = ['curl', 'ip.sb']
            result = subprocess.run(
                command, capture_output=True, text=True, check=True, timeout=10
            )
            ip_address = result.stdout.strip()
            
            if ip_address and '.' in ip_address:
                self.public_ip = ip_address
                if log_queue:
                    log_queue.put(f"[Checker] 成功获取本机公网IP: {self.public_ip} (通过 ip.sb)")
            else:
                 if log_queue:
                    log_queue.put(f"[Checker] [!] 调用curl ip.sb未能返回有效IP。响应: '{ip_address}'")
        except FileNotFoundError:
            if log_queue:
                log_queue.put("[Checker] [!] 'curl'命令未找到。请确保curl已安装并在系统PATH中。")
        except Exception as e:
            if log_queue:
                log_queue.put(f"[Checker] [!] 调用系统curl获取本机公网IP失败: {e}")

    def _get_proxy_location(self, ip: str, log_queue=None):
        """
        查询IP的地理位置，聚合多个API源并带缓存，优先国内源，结果翻译为中文。
        """
        if ip in self.location_cache:
            return self.location_cache[ip]
        location = "未知"
        
        # API 1: ip-api.com (国际源, 覆盖广)
        try:
            url = f"http://ip-api.com/json/{ip}?lang=zh-CN&fields=status,message,country"
            res = self.checker_session.get(url, timeout=2)
            res.raise_for_status()
            data = res.json()
            if data.get('status') == 'success':
                country = data.get('country', '')
                if country:
                    location = self.COUNTRY_NAME_MAP.get(country, country)
                    self.location_cache[ip] = location
                    return location
        except Exception as e:
            if log_queue:
                log_queue.put(f"[Checker] 查询 {ip} 地理位置 (ip-api) 失败: {e}")
            pass # 尝试下一个API
        # API 2: ip.taobao.com (国内源, 查国内IP快且准)
        try:
            url = f"https://ip.taobao.com/outGetIpInfo?ip={ip}&accessKey=alibaba-inc"
            res = self.checker_session.get(url, timeout=3)
            res.raise_for_status()
            data = res.json()
            if data.get('code') == 0 and 'data' in data:
                d = data['data']
                country = d.get('country', '')
                if country:
                    location = self.COUNTRY_NAME_MAP.get(country, country)
                    self.location_cache[ip] = location
                    return location
        except Exception as e:
            if log_queue:
                log_queue.put(f"[Checker] 查询 {ip} 地理位置 (taobao) 失败: {e}")
            pass # 尝试下一个API
        # API 3: ip.sb (备用源)
        try:
            url = f"https://api.ip.sb/geoip/{ip}"
            res = self.checker_session.get(url, timeout=3)
            res.raise_for_status()
            data = res.json()
            country = data.get('country', '')
            if country:
                location = self.COUNTRY_NAME_MAP.get(country, country)
                self.location_cache[ip] = location
                return location
        except Exception as e:
            if log_queue:
                log_queue.put(f"[Checker] 查询 {ip} 地理位置 (ip.sb) 失败: {e}")
            pass
            
        self.location_cache[ip] = location
        return location

    def _pre_check_proxy(self, proxy: str, log_queue=None):
        """TCP预检，快速判断端口是否开放。"""
        try:
            ip, port_str = proxy.split(':')
            with socket.create_connection((ip, int(port_str)), timeout=1.5):
                return True
        except Exception as e:
            if log_queue:
                log_queue.put(f"[Checker] TCP预检失败 {proxy}: {e}")
            return False

    def _full_check_proxy(self, proxy_info: dict, validation_mode: str = 'online', cancel_event=None, log_queue=None):
        """
        对单个代理进行完整的质量验证，此过程可随时取消。
        在每个阻塞网络操作前后，都会检查 cancel_event。
        """
        proxy = proxy_info['proxy']
        protocol = proxy_info['protocol']
        proxy_url = f"{protocol.lower()}://{proxy}"
        proxies_dict = {'http': proxy_url, 'https': proxy_url}
        result = {
            'proxy': proxy, 'protocol': protocol.upper(), 'status': 'Failed',
            'latency': float('inf'), 'speed': 0, 'anonymity': 'Unknown', 'location': 'N/A'
        }
        try:
            if cancel_event and cancel_event.is_set(): return None
            start_time = time.time()
            self.checker_session.head(self.validation_targets['latency_check'], proxies=proxies_dict, timeout=self.timeout).raise_for_status()
            result['latency'] = time.time() - start_time
            if cancel_event and cancel_event.is_set(): return None
            res_anon = self.checker_session.get(self.validation_targets['anonymity_check'], proxies=proxies_dict, timeout=self.timeout)
            res_anon.raise_for_status()
            data = res_anon.json()
            origin_ips_str = data.get('headers', {}).get('X-Forwarded-For', data.get('origin', ''))
            origin_ips = [ip.strip() for ip in origin_ips_str.split(',')]
            
            if self.public_ip and any(self.public_ip in ip for ip in origin_ips):
                result['anonymity'] = 'Transparent'
                # 透明代理，直接返回，不再测速
            elif len(origin_ips) > 1 or 'Via' in data.get('headers', {}):
                result['anonymity'] = 'Anonymous'
            else:
                result['anonymity'] = 'Elite'
            if cancel_event and cancel_event.is_set(): return None
            # 延迟低于7秒的才进行测速
            if result['latency'] <= 7.0:
                speed_check_url = self.validation_targets['latency_check'] if validation_mode == 'online' else self.validation_targets['speed_check']
                try:
                    start_speed = time.time()
                    speed_response = self.checker_session.get(speed_check_url, proxies=proxies_dict, timeout=15, stream=True)
                    speed_response.raise_for_status()
                    
                    content_size = 0
                    for chunk in speed_response.iter_content(chunk_size=8192):
                        if cancel_event and cancel_event.is_set():
                            speed_response.close() # 及时关闭连接
                            return None
                        content_size += len(chunk)
                    speed_duration = time.time() - start_speed
                    if speed_duration > 0 and content_size > 0:
                        # 计算速度，单位 Mbps
                        result['speed'] = (content_size / speed_duration) * 8 / (1000**2)
                except Exception as e:
                    if log_queue:
                        log_queue.put(f"[Checker] 测速失败 {proxy}: {e}")
                    pass # 测速失败不影响整体结果
            if cancel_event and cancel_event.is_set(): return None
            
            # 查询地理位置
            result['location'] = self._get_proxy_location(proxy.split(":")[0], log_queue)
            
            # 计算一个综合评分 (可选，用于排序)
            score = 0
            if result['anonymity'] == 'Elite':
                score += 50
            elif result['anonymity'] == 'Anonymous':
                score += 30
            # 速度加分
            score += min(result['speed'] * 2, 50) # 速度满分50分
            # 延迟扣分
            score -= min(result['latency'] * 10, 50) # 延迟最多扣50分
            result['score'] = max(score, 0) # 保证分数非负
            
            result['status'] = 'Working'
            return result
        except requests.RequestException as e:
            if log_queue:
                log_queue.put(f"[Checker] 验证失败 {proxy}: {e}")
            return result
        except Exception as e:
            if log_queue:
                log_queue.put(f"[Checker] 验证异常 {proxy}: {e}")
            return result

    def validate_all_proxies(self, proxies_by_protocol: dict, result_queue, log_queue, validation_mode='online', max_workers=100, cancel_event=None):
        """
        对一组代理进行完整的质量验证。
        这是Checker的核心入口，会将结果放入 result_queue。
        """
        all_proxies_flat = [{'proxy': p, 'protocol': proto} for proto, proxies in proxies_by_protocol.items() for p in proxies]
        total_proxies = len(all_proxies_flat)
        
        survivors = []
        # 代理数量太多时，跳过TCP预检，避免开销过大
        if total_proxies > 10000:
            log_queue.put(f"[!] 代理总数 ({total_proxies}) 超过10000，跳过TCP预检。")
            survivors = all_proxies_flat
        else:
            log_queue.put(f"[*] 阶段一：TCP预检开始，总数: {total_proxies}...")
            executor = ThreadPoolExecutor(max_workers=500)
            try:
                future_to_proxy = {executor.submit(self._pre_check_proxy, p['proxy'], log_queue): p for p in all_proxies_flat}
                for future in as_completed(future_to_proxy):
                    if cancel_event and cancel_event.is_set(): break
                    if future.result():
                        survivors.append(future_to_proxy[future])
            finally:
                # 如果任务被取消，不等线程池执行完毕
                executor.shutdown(wait=not (cancel_event and cancel_event.is_set()))
            log_queue.put(f"[+] 阶段一：TCP预检完成，幸存者: {len(survivors)} / {total_proxies}。")

        if cancel_event and cancel_event.is_set():
            log_queue.put("[Checker] 任务在TCP预检后被用户取消。")
            return # 直接返回，不往队列放任何东西

        log_queue.put("\n" + "="*20 + f" 阶段二：开始完整质量验证 " + "="*20)
        
        if not survivors:
            result_queue.put(None) # 正常结束
            return

        executor = ThreadPoolExecutor(max_workers=max_workers)
        try:
            futures = [executor.submit(self._full_check_proxy, p, validation_mode, cancel_event, log_queue) for p in survivors]
            for future in as_completed(futures):
                if cancel_event and cancel_event.is_set():
                    break
                try:
                    result = future.result()
                    if result:
                        result_queue.put(result)
                except Exception as e:
                    log_queue.put(f"[!] 验证器线程出现异常: {e}")
        finally:
            executor.shutdown(wait=not (cancel_event and cancel_event.is_set()))

        # 只有在任务未被取消的情况下，才发送结束信号(None)
        if not (cancel_event and cancel_event.is_set()):
            result_queue.put(None)
        else:
            log_queue.put("[Checker] 任务在完整验证阶段被用户取消。")

    # --- Rotator 核心方法 ---
    def clear(self):
        """清空所有代理，并重置内部状态。"""
        with self.lock:
            self.all_proxies = []
            self.proxies_by_country.clear()
            self.indices.clear()
            self.current_proxy = None

    def set_filters(self, region="All", quality_latency_ms=None):
        """设置轮换器当前使用的筛选条件。"""
        with self.lock:
            self.current_filter_region = region
            self.current_filter_quality_latency_ms = quality_latency_ms

    def add_proxy(self, proxy_info: dict):
        """添加一个新代理，如果代理地址已存在则忽略。"""
        with self.lock:
            proxy_address = proxy_info.get('proxy')
            if any(p.get('proxy') == proxy_address for p in self.all_proxies):
                return 
            proxy_info.setdefault('consecutive_failures', 0)
            proxy_info.setdefault('status', 'Working')
            self.all_proxies.append(proxy_info)
            country = proxy_info.get('location', 'Unknown')
            self.proxies_by_country[country].append(proxy_info)

    def remove_proxy(self, proxy_address: str):
        """根据代理地址移除一个代理。"""
        with self.lock:
            proxy_to_remove = None
            for p_info in self.all_proxies:
                if p_info.get('proxy') == proxy_address:
                    proxy_to_remove = p_info
                    break
            
            if proxy_to_remove:
                self.all_proxies.remove(proxy_to_remove)
                
                country = proxy_to_remove.get('location', 'Unknown')
                if country in self.proxies_by_country:
                    try:
                        self.proxies_by_country[country].remove(proxy_to_remove)
                        if not self.proxies_by_country[country]:
                            del self.proxies_by_country[country]
                    except ValueError:
                        pass
                
                if self.current_proxy and self.current_proxy.get('proxy') == proxy_address:
                    self.current_proxy = None
                return True
            return False

    def report_failure(self, proxy_address: str):
        """
        报告一个代理连接失败，立即将其状态设置为不可用。
        这个方法是线程安全的。
        """
        with self.lock:
            for p_info in self.all_proxies:
                if p_info.get('proxy') == proxy_address:
                    p_info['status'] = 'Unavailable'
                    return

    def get_proxy_by_address(self, proxy_address: str):
        """根据代理地址查询代理的详细信息。"""
        with self.lock:
            for p_info in self.all_proxies:
                if p_info.get('proxy') == proxy_address:
                    return p_info
            return None

    def update_proxy(self, proxy_address: str, update_data: dict):
        """更新指定代理的信息，例如状态、延迟等。"""
        with self.lock:
            for p_info in self.all_proxies:
                if p_info.get('proxy') == proxy_address:
                    p_info.update(update_data)
                    return True
            return False

    def get_all_proxies_for_revalidation(self):
        """获取所有代理的副本，用于重新验证。"""
        with self.lock:
            return list(self.all_proxies)

    def get_active_proxies_count(self) -> int:
        """统计当前状态为 'Working' 的代理数量。"""
        with self.lock:
            return sum(1 for p in self.all_proxies if p.get('status') == 'Working')

    def get_available_regions_with_counts(self, quality_latency_ms=None) -> dict:
        """按地区统计 'Working' 状态的代理数量，支持按延迟筛选。"""
        with self.lock:
            counts = defaultdict(int)
            for p_info in self.all_proxies:
                if p_info.get('status') != 'Working':
                    continue
                
                if quality_latency_ms is not None:
                    latency_ms = p_info.get('latency', float('inf')) * 1000
                    if latency_ms > quality_latency_ms:
                        continue
                region = p_info.get('location', 'Unknown')
                counts[region] += 1
            return dict(counts)

    def get_next_proxy(self):
        """根据内部存储的筛选条件，轮换获取下一个可用代理，并按分数排序。"""
        with self.lock:
            candidate_proxies = []
            
            # 使用内部存储的过滤器
            effective_region = self.current_filter_region
            effective_latency = self.current_filter_quality_latency_ms
            for p in self.all_proxies:
                if p.get('status') == 'Working':
                    region_match = (effective_region == "All" or p.get('location') == effective_region)
                    
                    quality_match = True
                    if effective_latency is not None:
                        latency_ms = p.get('latency', float('inf')) * 1000
                        quality_match = (latency_ms <= effective_latency)
                    if region_match and quality_match:
                        candidate_proxies.append(p)
            
            if not candidate_proxies:
                # 如果当前条件下无代理, 尝试放宽条件(不限区域和延迟)
                if effective_region != "All" or effective_latency is not None:
                    original_region = self.current_filter_region
                    original_latency = self.current_filter_quality_latency_ms
                    self.set_filters("All", None)
                    result = self.get_next_proxy()
                    self.set_filters(original_region, original_latency) # 恢复之前的过滤器
                    return result
                self.current_proxy = None
                return None

            # 按评分降序排列
            candidate_proxies.sort(key=lambda p: p.get('score', 0), reverse=True)
            
            quality_key = f"lt{effective_latency}" if effective_latency is not None else "any"
            index_key = f"{effective_region}_{quality_key}"
            current_idx = self.indices.get(index_key, -1)
            next_idx = (current_idx + 1) % len(candidate_proxies)
            self.indices[index_key] = next_idx
            
            self.current_proxy = candidate_proxies[next_idx]
            return self.current_proxy

    def get_current_proxy(self):
        """获取当前正在使用的代理。"""
        with self.lock:
            if self.current_proxy and self.current_proxy.get('status') != 'Working':
                self.current_proxy = None
            return self.current_proxy

    def set_current_proxy_by_address(self, proxy_address: str):
        """根据地址手动设置当前代理，代理必须可用。"""
        with self.lock:
            for p_info in self.all_proxies:
                if p_info.get('proxy') == proxy_address and p_info.get('status') == 'Working':
                    self.current_proxy = p_info
                    return p_info
            return None

    # --- 新增的整合方法 ---
    def refresh_proxies(self, log_queue, cancel_event=None):
        """
        高级整合方法：先清空现有代理，然后从网络抓取新代理，再对其进行验证，最后添加到管理器中。
        """
        self.clear()
        
        # Step 1: Fetch
        log_queue.put("[Manager] 开始抓取代理...")
        fetched_proxies_dict = self.fetch_all_proxies(log_queue, cancel_event)
        if cancel_event and cancel_event.is_set():
            log_queue.put("[Manager] 代理抓取阶段被取消。")
            return 0

        # Step 2: Validate
        log_queue.put("[Manager] 开始验证代理...")
        # 初始化本机IP
        self.initialize_public_ip(log_queue)
        from queue import Queue
        result_queue = Queue()
        self.validate_all_proxies(fetched_proxies_dict, result_queue, log_queue, cancel_event=cancel_event)
        
        # Step 3: Add to Manager
        validated_count = 0
        while True:
            if cancel_event and cancel_event.is_set():
                log_queue.put("[Manager] 代理验证/添加阶段被取消。")
                break
            result = result_queue.get()
            if result is None: # 结束信号
                break
            if result['status'] == 'Working':
                self.add_proxy(result)
                validated_count += 1

        log_queue.put(f"[+] 代理刷新完成，共验证并添加 {validated_count} 个可用代理。")
        return validated_count


    # ========== 新增：启动本地代理服务 ==========
    def start_local_proxy_service(self, http_host="127.0.0.1", http_port=8888, socks5_host="127.0.0.1", socks5_port=1080, auto_refresh_minutes=0):
        if not self.log_queue:
            raise ValueError("请先设置 log_queue")
        if not self._searcher:
            self._searcher = self.AssetSearcher(self.log_queue)
        self._proxy_server = self.ProxyServer(self, http_host, http_port, socks5_host, socks5_port, self.log_queue)
        self._proxy_server.start_all()
        self._auto_refresh_minutes = auto_refresh_minutes
        if auto_refresh_minutes > 0:
            self._refresh_thread = threading.Thread(target=self._auto_refresh_proxies, daemon=True)
            self._refresh_thread.start()
            self.log(f"代理自动刷新已启用，每 {auto_refresh_minutes} 分钟执行一次。")

    def stop_local_proxy_service(self):
        if self._proxy_server:
            self._proxy_server.stop_all()
        if self._refresh_thread and self._refresh_thread.is_alive():
            # 无法直接中断线程，但可设标志位
            self._auto_refresh_minutes = 0
            self._refresh_thread.join(timeout=2)

    def _auto_refresh_proxies(self):
        while self._auto_refresh_minutes > 0:
            try:
                self.log("[🔄] 自动刷新：从资产引擎获取最新代理...")
                # 这里应使用上次的配置，或提供默认配置
                default_settings = {
                    "fofa": {"enabled": True, "key": "your_email:your_key", "query": 'protocol="socks5"', "size": 50},
                    "quake": {"enabled": False},
                    "hunter": {"enabled": False}
                }
                proxies = self._searcher.search_all(default_settings)
                if proxies:
                    proxy_list = [{'proxy': p, 'protocol': 'SOCKS5'} for p in proxies]
                    self.update_proxies(proxy_list)
                    self.log(f"[✅] 自动刷新完成，新增 {len(proxies)} 个代理。")
                else:
                    self.log("[⚠️] 自动刷新未获取到新代理。")
            except Exception as e:
                self.log(f"[❌] 自动刷新失败: {e}")
            # 简单的等待，可以被中断
            for _ in range(self._auto_refresh_minutes * 60):
                time.sleep(1)
                if self._auto_refresh_minutes <= 0:
                     return # 如果标志位被清除，则退出循环

    # ========== 新增：从资产引擎获取代理 ==========
    def fetch_proxies_from_engines(self, settings):
        if not self._searcher:
            self._searcher = self.AssetSearcher(self.log_queue)
        proxies = self._searcher.search_all(settings)
        if proxies:
            proxy_list = [{'proxy': p, 'protocol': 'SOCKS5'} for p in proxies]
            self.update_proxies(proxy_list)
            self.log(f"[✅] 从资产引擎加载 {len(proxies)} 个代理。")
            return True
        else:
            self.log("[⚠️] 未从资产引擎获取到代理。")
            return False

    # ========== 新增：更新代理池（供轮换器使用） ==========
    def update_proxies(self, proxy_list):
        with self.lock:
            self.all_proxies = proxy_list
            self.proxies_by_country.clear()
            for p in proxy_list:
                country = p.get('location', 'Unknown')
                self.proxies_by_country[country].append(p)
            self.indices.clear()
            self.current_proxy = None if not proxy_list else None

    # ========== 新增：获取当前/下一个代理（供ProxyServer调用） ==========
    def get_current_proxy(self):
        with self.lock:
            if not self.current_proxy and self.all_proxies:
                self.current_proxy = self.all_proxies[0]
            return self.current_proxy

    def get_next_proxy(self):
        with self.lock:
            if not self.all_proxies:
                return None
            self.indices['global'] = (self.indices['global'] + 1) % len(self.all_proxies)
            self.current_proxy = self.all_proxies[self.indices['global']]
            return self.current_proxy

    # ========== 新增：设置日志队列 ==========
    def set_log_queue(self, log_queue):
        self.log_queue = log_queue

    def log(self, message):
        if self.log_queue:
            self.log_queue.put(f"[Manager] {message}")
