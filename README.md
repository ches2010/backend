# Proxy Hub

一个功能强大的 Python 代理管理器，集成了代理获取、验证、轮换和服务功能。

## 功能

*   **多源获取**: 从多种 API 和网页爬取 HTTP/HTTPS/SOCKS4/SOCKS5 代理。
*   **质量验证**: 对代理进行延迟、速度、匿名度和地理位置的全面检测。
*   **智能轮换**: 提供按地区、延迟等条件筛选的代理轮换功能。
*   **本地服务**: 启动本地 HTTP 和 SOCKS5 代理服务器，上游代理自动轮换。
*   **资产引擎集成**: (可选) 从 FOFA, Quake, Hunter 等资产搜索引擎获取代理。
*   **CLI 工具**: 提供命令行界面进行代理刷新等操作。
*   **Web UI (计划中)**: 提供图形化界面查看代理列表和控制服务。
*   **hq.py 兼容**: 兼容并优化了原始的 `hq.py` 代理获取脚本。

## 目录结构

proxy_hub/
├── README.md
├── requirements.txt
├── config.json
├── hq.py
├── proxy_manager.py
├── main.py
├── web_ui/
│   ├── index.html
│   ├── static/
│   │   ├── style.css
│   │   └── script.js
│   └── templates/ (如果用Flask)
└── utils/
    └── __init__.py

## 安装

1.  **克隆仓库**:
    ```bash
    git clone <your-repo-url> proxy_hub
    cd proxy_hub
    ```
2.  **创建虚拟环境 (推荐)**:
    ```bash
    python -m venv venv
    # Windows
    venv\Scripts\activate
    # macOS/Linux
    source venv/bin/activate
    ```
3.  **安装依赖**:
    ```bash
    pip install -r requirements.txt
    ```

## 配置

编辑 `config.json` 文件以设置代理服务端口、资产引擎密钥等。

*   `proxy_server`: 配置本地代理服务。
    *   `http/socks5`: 设置 HTTP/SOCKS5 服务的主机和端口。
    *   `auto_refresh_minutes`: 设置自动刷新代理的间隔（分钟），设为 0 禁用。
*   `asset_engines`: 配置资产搜索引擎（如 FOFA, Quake, Hunter）。
    *   `enabled`: 是否启用该引擎。
    *   `key`: 你的 API 密钥。
    *   `query`: 搜索查询语句。
    *   `size`: 每次搜索返回的最大结果数。
*   `validation`: 配置代理验证参数。
    *   `timeout`: 验证单个代理的超时时间（秒）。
    *   `max_workers`: 验证时使用的最大并发线程数。

## 使用方法

### 1. 启动本地代理服务

```bash
python main.py --mode service
```
这将根据 `config.json` 中的配置启动 HTTP 和 SOCKS5 代理服务。

### 2. 通过 CLI 刷新代理

```bash
python main.py --mode refresh
```
这将在命令行中执行一次代理获取和验证，并将结果存储在 `ProxyManager` 内部。

### 3. 运行 hq.py 脚本

```bash
python main.py --mode hq --output-dir ./output
```
这将执行原始的 `hq.py` 逻辑，获取代理并保存到指定目录（默认为当前目录）。

### 4. 使用 Web UI (当前为静态演示)

1.  在浏览器中打开 `web_ui/index.html`。
2.  当前后端 API 未实现，页面显示的是模拟数据。
3.  实际部署时，需要一个后端服务（例如 Flask）来提供 API 接口供前端调用。

## 注意事项

*   本工具用于学习和研究目的，请遵守相关法律法规。
*   部分代理源可能不稳定或已失效，请根据实际情况调整 `proxy_manager.py` 中的源列表。
*   资产搜索引擎（FOFA, Quake, Hunter）需要有效的 API 密钥才能使用。
*   代理验证会消耗网络资源和时间，请根据网络环境调整 `config.json` 中的 `timeout` 和 `max_workers` 参数。

```
