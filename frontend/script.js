document.addEventListener('DOMContentLoaded', () => {
    // ---- Authentication ----
    const authOverlay = document.getElementById('auth-overlay');
    const loginBtn = document.getElementById('login-btn');
    loginBtn.addEventListener('click', () => {
        authOverlay.classList.add('hidden');
        initializeApp();
    });

    // ---- Theme Toggle ----
    const themeToggle = document.getElementById('theme-toggle');
    themeToggle.addEventListener('change', (e) => {
        document.documentElement.setAttribute('data-theme', e.target.checked ? 'dark' : 'light');
        updateAllChartsTheme();
    });

    // ---- Globals & Chart instances ----
    const API_BASE = '/api';
    let charts = {};
    let isLiveRefresh = false;
    let refreshInterval = null;

    // ---- Filters Elements ----
    const startDate = document.getElementById('filter-start');
    const endDate = document.getElementById('filter-end');
    const regionFilter = document.getElementById('filter-region');
    const categoryFilter = document.getElementById('filter-category');

    function initializeApp() {
        populateFilters().then(() => {
            initCharts();
            fetchAllData();
            setupEventListeners();
        });
    }

    async function populateFilters() {
        try {
            const res = await fetch(`${API_BASE}/filters`);
            const data = await res.json();
            
            if(data.date_bounds) {
                startDate.value = data.date_bounds.min;
                endDate.value = data.date_bounds.max;
            }
            if(data.regions) {
                regionFilter.innerHTML = data.regions.map(r => `<option value="${r}">${r}</option>`).join('');
            }
            if(data.categories) {
                categoryFilter.innerHTML = data.categories.map(c => `<option value="${c}">${c}</option>`).join('');
            }
        } catch (e) {
            console.error('Failed to load filters', e);
        }
    }

    function setupEventListeners() {
        const filters = [startDate, endDate, regionFilter, categoryFilter];
        filters.forEach(f => f.addEventListener('change', fetchAllData));

        // PDF Generation
        document.getElementById('btn-pdf').addEventListener('click', () => {
            const element = document.getElementById('dashboard-content');
            const opt = {
                margin: 0.5,
                filename: 'sales_report.pdf',
                image: { type: 'jpeg', quality: 0.98 },
                html2canvas: { scale: 2, useCORS: true },
                jsPDF: { unit: 'in', format: 'a3', orientation: 'landscape' }
            };
            html2pdf().set(opt).from(element).save();
        });

        // CSV Generation
        document.getElementById('btn-report').addEventListener('click', () => {
            const q = getQueryParams();
            window.open(`${API_BASE}/report?${q}`, '_blank');
        });

        // Live Refresh
        document.getElementById('refresh-toggle').addEventListener('change', (e) => {
            isLiveRefresh = e.target.checked;
            if(isLiveRefresh) {
                refreshInterval = setInterval(fetchAllData, 5000); // 5 seconds
            } else {
                clearInterval(refreshInterval);
            }
        });
    }

    function getQueryParams() {
        const params = new URLSearchParams();
        if(startDate.value) params.append('start', startDate.value);
        if(endDate.value) params.append('end', endDate.value);
        if(regionFilter.value) params.append('region', regionFilter.value);
        if(categoryFilter.value) params.append('category', categoryFilter.value);
        return params.toString();
    }

    async function fetchAllData() {
        const q = getQueryParams();
        
        // Fetch KPIs
        fetch(`${API_BASE}/kpis?${q}`).then(r=>r.json()).then(data => {
            document.getElementById('kpi-sales').innerText = `₹${(data.total_sales || 0).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})}`;
            document.getElementById('kpi-orders').innerText = (data.total_orders || 0).toLocaleString();
            document.getElementById('kpi-aov').innerText = `₹${(data.average_order_value || 0).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})}`;
            document.getElementById('kpi-profit').innerText = `₹${(data.total_profit || 0).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})}`;
        });

        // Fetch Monthly Sales
        fetch(`${API_BASE}/sales_by_month?${q}`).then(r=>r.json()).then(data => {
            updateChart('monthlySalesChart', data.labels, data.values);
        });

        // Fetch Region Sales
        fetch(`${API_BASE}/region_sales?${q}`).then(r=>r.json()).then(data => {
            updateChart('regionSalesChart', data.labels, data.values);
        });

        // Fetch Top Products
        fetch(`${API_BASE}/top_products?${q}`).then(r=>r.json()).then(data => {
            updateChart('topProductsChart', data.labels, data.values);
        });

        // Fetch Category Sales
        fetch(`${API_BASE}/category_sales?${q}`).then(r=>r.json()).then(data => {
            updateChart('categorySalesChart', data.labels, data.values);
        });

        // Fetch Profit vs Discount
        fetch(`${API_BASE}/profit_vs_discount?${q}`).then(r=>r.json()).then(data => {
            if(charts['profitDiscountChart'] && data.data) {
                charts['profitDiscountChart'].data.datasets[0].data = data.data;
                charts['profitDiscountChart'].update();
            }
        });

        // Fetch Smart Insights
        fetch(`${API_BASE}/smart_insights?${q}`).then(r=>r.json()).then(data => {
            if(data.insights) {
                const list = document.getElementById('insights-list');
                list.innerHTML = data.insights.map(i => `<li><span class="icon">${i.icon}</span><span class="text">${i.text}</span></li>`).join('');
                
                const summaryP = document.getElementById('insights-summary-text');
                summaryP.innerText = data.summary || 'No data generated.';
                
                // Set trend color class
                summaryP.className = ''; // reset
                if(data.trend_color === 'green') summaryP.classList.add('trend-green');
                else if(data.trend_color === 'red') summaryP.classList.add('trend-red');
            }
        });
    }

    const getColors = () => {
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        return {
            text: isDark ? '#f8fafc' : '#1e293b',
            grid: isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)'
        }
    };

    function initCharts() {
        Chart.defaults.font.family = 'Inter';
        Chart.defaults.color = getColors().text;
        
        // Monthly line chart
        const ctxMonthly = document.getElementById('monthlySalesChart').getContext('2d');
        charts['monthlySalesChart'] = new Chart(ctxMonthly, {
            type: 'line',
            data: { labels: [], datasets: [{ label: 'Sales', data: [], borderColor: '#4f46e5', backgroundColor: 'rgba(79, 70, 229, 0.2)', fill: true, tension: 0.3 }] },
            options: { responsive: true, maintainAspectRatio: false }
        });

        // Region Doughnut
        const ctxRegion = document.getElementById('regionSalesChart').getContext('2d');
        charts['regionSalesChart'] = new Chart(ctxRegion, {
            type: 'doughnut',
            data: { labels: [], datasets: [{ data: [], backgroundColor: ['#4f46e5', '#06b6d4', '#10b981', '#f59e0b', '#ec4899', '#8b5cf6'], cursor: 'pointer' }] },
            options: { 
                responsive: true, maintainAspectRatio: false, 
                plugins: { legend: { position: 'right' } },
                onHover: (e, elements) => {
                    e.native.target.style.cursor = elements[0] ? 'pointer' : 'default';
                },
                onClick: (e, elements) => {
                    if (elements.length > 0) {
                        const label = charts['regionSalesChart'].data.labels[elements[0].index];
                        regionFilter.value = label;
                        fetchAllData();
                    }
                }
            }
        });

        // Top products Bar
        const ctxTop = document.getElementById('topProductsChart').getContext('2d');
        charts['topProductsChart'] = new Chart(ctxTop, {
            type: 'bar',
            data: { labels: [], datasets: [{ label: 'Sales', data: [], backgroundColor: '#06b6d4' }] },
            options: { responsive: true, maintainAspectRatio: false, indexAxis: 'y' }
        });

        // Category Bar
        const ctxCat = document.getElementById('categorySalesChart').getContext('2d');
        charts['categorySalesChart'] = new Chart(ctxCat, {
            type: 'bar',
            data: { labels: [], datasets: [{ label: 'Sales', data: [], backgroundColor: '#10b981' }] },
            options: { 
                responsive: true, maintainAspectRatio: false,
                onHover: (e, elements) => {
                    e.native.target.style.cursor = elements[0] ? 'pointer' : 'default';
                },
                onClick: (e, elements) => {
                    if (elements.length > 0) {
                        const label = charts['categorySalesChart'].data.labels[elements[0].index];
                        categoryFilter.value = label;
                        fetchAllData();
                    }
                }
            }
        });

        // Profit vs Discount Scatter
        const ctxScatter = document.getElementById('profitDiscountChart').getContext('2d');
        charts['profitDiscountChart'] = new Chart(ctxScatter, {
            type: 'scatter',
            data: { datasets: [{ label: 'Transactions', data: [], backgroundColor: 'rgba(236, 72, 153, 0.5)' }] },
            options: { 
                responsive: true, maintainAspectRatio: false,
                scales: { x: { title: { display: true, text: 'Discount' } }, y: { title: { display: true, text: 'Profit' } } }
            }
        });
    }

    function updateChart(id, labels, data) {
        if(charts[id]) {
            charts[id].data.labels = labels;
            charts[id].data.datasets[0].data = data;
            charts[id].update();
        }
    }

    function updateAllChartsTheme() {
        const colors = getColors();
        Chart.defaults.color = colors.text;
        Object.values(charts).forEach(chart => {
            if(chart.options.scales) {
                if(chart.options.scales.x) {
                    chart.options.scales.x.ticks = chart.options.scales.x.ticks || {};
                    chart.options.scales.x.ticks.color = colors.text;
                    chart.options.scales.x.grid = chart.options.scales.x.grid || {};
                    chart.options.scales.x.grid.color = colors.grid;
                }
                if(chart.options.scales.y) {
                    chart.options.scales.y.ticks = chart.options.scales.y.ticks || {};
                    chart.options.scales.y.ticks.color = colors.text;
                    chart.options.scales.y.grid = chart.options.scales.y.grid || {};
                    chart.options.scales.y.grid.color = colors.grid;
                }
            }
            chart.update();
        });
    }
});
