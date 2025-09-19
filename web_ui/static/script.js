// web_ui/static/script.js

// --- 配置 ---
// 注意：在真实的部署环境中，这个地址需要指向你的后端API服务器
const API_BASE_URL = 'http://127.0.0.1:5000/api'; // 示例地址，需要后端支持

// --- DOM 元素 ---
const refreshBtn = document.getElementById('refreshBtn');
const startServiceBtn = document.getElementById('startServiceBtn');
const stopServiceBtn = document.getElementById('stopServiceBtn');
const serviceStatusEl = document.getElementById('serviceStatus');
const regionFilterEl = document.getElementById('regionFilter');
const maxLatencyFilterEl = document.getElementById('maxLatencyFilter');
const applyFiltersBtn = document.getElementById('applyFiltersBtn');
const totalProxiesEl = document.getElementById('totalProxies');
const activeProxiesEl = document.getElementById('activeProxies');
const proxyTableBody = document.querySelector('#proxyTable tbody');

// --- 状态变量 ---
let currentProxies = [];
let availableRegions = [];

// --- 辅助函数 ---

function updateServiceStatus(statusText, isError = false) {
    serviceStatusEl.textContent = statusText;
    serviceStatusEl.style.color = isError ? 'red' : 'black';
}

function updateStats(total, active) {
    totalProxiesEl.textContent = total;
    activeProxiesEl.textContent = active;
}

function populateRegionFilter(regionsWithCounts) {
    // 清空现有选项
    regionFilterEl.innerHTML = '<option value="All">全部</option>';
    availableRegions = Object.keys(regionsWithCounts).sort();
    availableRegions.forEach(region => {
        const option = document.createElement('option');
        option.value = region;
        // 可以显示地区和数量，例如 "中国 (15)"
        option.textContent = `${region} (${regionsWithCounts[region]})`;
        regionFilterEl.appendChild(option);
    });
}

function renderProxyTable(proxies) {
    proxyTableBody.innerHTML = ''; // 清空现有行

    if (!proxies || proxies.length === 0) {
        const row = document.createElement('tr');
        const cell = document.createElement('td');
        cell.colSpan = 7; // 跨所有列
        cell.textContent = '没有可用的代理。';
        cell.style.textAlign = 'center';
        row.appendChild(cell);
        proxyTableBody.appendChild(row);
        return;
    }

    proxies.forEach(proxy => {
        const row = document.createElement('tr');

        const addressCell = document.createElement('td');
        addressCell.textContent = proxy.proxy;

        const protocolCell = document.createElement('td');
        protocolCell.textContent = proxy.protocol;

        const latencyCell = document.createElement('td');
        latencyCell.textContent = proxy.latency !== undefined ? proxy.latency.toFixed(3) : 'N/A';

        const speedCell = document.createElement('td');
        speedCell.textContent = proxy.speed !== undefined ? proxy.speed.toFixed(2) : 'N/A';

        const anonymityCell = document.createElement('td');
        anonymityCell.textContent = proxy.anonymity || 'N/A';

        const locationCell = document.createElement('td');
        locationCell.textContent = proxy.location || 'N/A';

        const scoreCell = document.createElement('td');
        scoreCell.textContent = proxy.score !== undefined ? proxy.score.toFixed(0) : 'N/A';

        row.appendChild(addressCell);
        row.appendChild(protocolCell);
        row.appendChild(latencyCell);
        row.appendChild(speedCell);
        row.appendChild(anonymityCell);
        row.appendChild(locationCell);
        row.appendChild(scoreCell);

        proxyTableBody.appendChild(row);
    });
}

// --- API 调用函数 (模拟) ---

// 注意：以下函数是模拟的，因为后端API尚未实现。
// 在实际应用中，你需要用 fetch 或 axios 替换这些模拟函数。

async function fetchProxies(filters = {}) {
    // 模拟 API 延迟
    await new Promise(resolve => setTimeout(resolve, 500));
    
    // 模拟数据
    const mockData = {
        proxies: [
            { proxy: "192.168.1.1:8080", protocol: "HTTP", latency: 0.123, speed: 5.67, anonymity: "Elite", location: "中国", score: 95 },
            { proxy: "10.0.0.1:1080", protocol: "SOCKS5", latency: 0.456, speed: 2.34, anonymity: "Anonymous", location: "美国", score: 78 },
            { proxy: "172.16.0.1:80", protocol: "HTTP", latency: 1.234, speed: 0.98, anonymity: "Transparent", location: "德国", score: 45 },
        ],
        total: 100,
        active: 3,
        regions: { "中国": 50, "美国": 30, "德国": 20 }
    };
    return mockData;
}

async function refreshProxies() {
    updateServiceStatus('正在刷新代理...');
    try {
        const data = await fetchProxies();
        currentProxies = data.proxies;
        updateStats(data.total, data.active);
        populateRegionFilter(data.regions);
        renderProxyTable(currentProxies);
        updateServiceStatus('代理刷新成功。');
    } catch (error) {
        console.error('刷新代理失败:', error);
        updateServiceStatus('刷新代理失败。', true);
    }
}

async function startService() {
    updateServiceStatus('正在启动服务...');
    // 模拟API调用
    await new Promise(resolve => setTimeout(resolve, 300));
    updateServiceStatus('服务已启动。');
}

async function stopService() {
    updateServiceStatus('正在停止服务...');
    // 模拟API调用
    await new Promise(resolve => setTimeout(resolve, 300));
    updateServiceStatus('服务已停止。');
}

async function applyFilters() {
    const region = regionFilterEl.value;
    const maxLatency = parseFloat(maxLatencyFilterEl.value) || null;
    
    updateServiceStatus('正在应用筛选...');
    try {
        // 在实际应用中，这里应该将筛选条件发送给后端
        // const data = await fetchProxies({ region, maxLatency });
        // 为了演示，我们直接在前端筛选模拟数据
        let filtered = [...currentProxies];
        if (region !== 'All') {
            filtered = filtered.filter(p => p.location === region);
        }
        if (maxLatency !== null) {
            filtered = filtered.filter(p => p.latency !== undefined && p.latency * 1000 <= maxLatency);
        }
        renderProxyTable(filtered);
        updateServiceStatus('筛选已应用。');
    } catch (error) {
        console.error('应用筛选失败:', error);
        updateServiceStatus('应用筛选失败。', true);
    }
}

// --- 事件监听器 ---

refreshBtn.addEventListener('click', refreshProxies);
startServiceBtn.addEventListener('click', startService);
stopServiceBtn.addEventListener('click', stopService);
applyFiltersBtn.addEventListener('click', applyFilters);

// --- 初始化 ---
document.addEventListener('DOMContentLoaded', async () => {
    updateServiceStatus('正在加载...');
    await refreshProxies(); // 页面加载时自动刷新一次
});




