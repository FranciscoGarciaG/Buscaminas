// Fertilizantes para el Bienestar 2026 - Dashboard App Logic

let globalData = {};
let currentState = 'NACIONAL'; // Default to NACIONAL
let selectedDate = '2026-07-23';

// Chart Instances
let chartDerechohabientes = null;
let chartDap = null;
let chartUrea = null;
let chartHa = null;
let chartGenero = null;
let chartEdades = null;
let chartEntregas = null;

// Donut Center Text Plugin
const centerTextPlugin = {
    id: 'centerText',
    beforeDraw(chart) {
        if (!chart.config.options.plugins.centerText) return;
        const { ctx, chartArea: { left, top, width, height } } = chart;
        ctx.save();
        const text = chart.config.options.plugins.centerText.text || '';
        const color = chart.config.options.plugins.centerText.color || '#333';
        const fontSize = chart.config.options.plugins.centerText.fontSize || 14;

        ctx.font = `800 ${fontSize}px Montserrat, sans-serif`;
        ctx.fillStyle = color;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(text, left + width / 2, top + height / 2);
        ctx.restore();
    }
};

Chart.register(centerTextPlugin);
if (window.ChartDataLabels) {
    Chart.register(ChartDataLabels);
}

// Globally disable Chart.js re-render animations for instant lag-free switching
Chart.defaults.animation = false;

document.addEventListener('DOMContentLoaded', () => {
    loadData();

    document.getElementById('state-select').addEventListener('change', (e) => {
        currentState = e.target.value;
        updateDashboard();
    });

    document.getElementById('date-picker').addEventListener('change', (e) => {
        selectedDate = e.target.value;
        updateDateAtencion();
    });

    const btnPdf = document.getElementById('btn-export-pdf');
    if (btnPdf) {
        btnPdf.addEventListener('click', exportToPDF);
    }
});

async function loadData() {
    try {
        const resp = await fetch('dashboard_data.json');
        if (!resp.ok) throw new Error('Data file not found');
        globalData = await resp.json();
        
        populateStateDropdown();
        updateDashboard();
    } catch (err) {
        console.error('Error loading dataset:', err);
        document.getElementById('data-status').textContent = '⚠️ Error cargando datos';
    }
}

function populateStateDropdown() {
    const select = document.getElementById('state-select');
    select.innerHTML = '';

    const states = Object.keys(globalData).sort();
    
    const ordered = [];
    if (states.includes('NACIONAL')) ordered.push('NACIONAL');
    if (states.includes('MORELOS')) ordered.push('MORELOS');
    
    states.forEach(s => {
        if (s !== 'MORELOS' && s !== 'NACIONAL') ordered.push(s);
    });

    ordered.forEach(st => {
        const opt = document.createElement('option');
        opt.value = st;
        opt.textContent = st === 'NACIONAL' ? '🇲🇽 A NIVEL NACIONAL' : st;
        if (st === currentState) opt.selected = true;
        select.appendChild(opt);
    });
}

function updateDashboard() {
    const sdata = globalData[currentState];
    if (!sdata) return;

    // 1. Banner Titles
    const titleText = currentState === 'NACIONAL' 
        ? 'ENTREGA DE FERTILIZANTE A NIVEL NACIONAL 2026'
        : `ENTREGA DE FERTILIZANTE EN EL ESTADO DE ${currentState} 2026`;
    document.getElementById('banner-title').textContent = titleText;

    // Pick max date if available
    const dates = Object.keys(sdata.atenciones_por_fecha || {}).sort();
    const maxDate = dates.length > 0 ? dates[dates.length - 1] : selectedDate;
    document.getElementById('banner-subtitle').textContent = `AL ${formatFechaMexican(maxDate)}`;
    
    if (dates.length > 0 && !dates.includes(selectedDate)) {
        selectedDate = maxDate;
        document.getElementById('date-picker').value = selectedDate;
    }

    // 2. Metas Section
    document.getElementById('meta-derechohabientes').textContent = formatNum(sdata.meta.productores);
    document.getElementById('meta-urea').textContent = formatDec(sdata.meta.urea_ton, 3);
    document.getElementById('meta-dap').textContent = formatDec(sdata.meta.dap_ton, 3);
    document.getElementById('meta-hectareas').textContent = formatNum(sdata.meta.hectareas);

    // 3. Avance Section Values
    document.getElementById('val-atendidos').textContent = formatNum(sdata.avance.atendidos);
    document.getElementById('val-dap').textContent = formatDec(sdata.avance.dap_entregada, 2);
    document.getElementById('val-urea').textContent = formatDec(sdata.avance.urea_entregada, 3);
    document.getElementById('val-ha').textContent = formatNum(sdata.avance.ha_atendidas);

    // Render Donut Charts with comfortable padding to prevent clipping
    renderDonutChart('chart-derechohabientes', sdata.avance.pct_derechohabientes, '#4a1521', (chart) => chartDerechohabientes = chart, chartDerechohabientes);
    renderDonutChart('chart-dap', sdata.avance.pct_dap, '#4a1521', (chart) => chartDap = chart, chartDap, 11);
    renderDonutChart('chart-urea', sdata.avance.pct_urea, '#0d3629', (chart) => chartUrea = chart, chartUrea, 11);
    renderDonutChart('chart-ha', sdata.avance.pct_ha, '#a38148', (chart) => chartHa = chart, chartHa);

    // Date Atencion
    updateDateAtencion();

    // 4. Tri-Column Breakdown
    renderGeneroChart(sdata.genero);
    renderCultivosTable(sdata.cultivos, sdata.avance.atendidos, sdata.avance.ha_atendidas);
    renderEdadesChart(sdata.edades);

    // 5. Entregas Chart
    renderEntregasChart(sdata);
}

function updateDateAtencion() {
    const sdata = globalData[currentState];
    if (!sdata) return;

    const count = sdata.atenciones_por_fecha[selectedDate] || 0;
    document.getElementById('val-atendidos-fecha').textContent = formatNum(count);
    document.getElementById('label-fecha-atencion').textContent = formatFechaMexican(selectedDate);
}

// Donut Chart Helper with padding to prevent clipping
function renderDonutChart(canvasId, pct, color, setRef, existingRef, fontSize = 13) {
    if (existingRef) existingRef.destroy();

    const ctx = document.getElementById(canvasId).getContext('2d');
    const remaining = Math.max(0, 100 - pct);

    const chart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            datasets: [{
                data: [pct, remaining],
                backgroundColor: [color, '#e2dac9'],
                borderWidth: 0
            }]
        },
        options: {
            cutout: '70%',
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            layout: {
                padding: { top: 4, bottom: 4, left: 4, right: 4 }
            },
            plugins: {
                legend: { display: false },
                tooltip: { enabled: false },
                datalabels: { display: false },
                centerText: {
                    text: `${pct.toFixed(2)}%`,
                    color: color,
                    fontSize: fontSize
                }
            }
        }
    });

    setRef(chart);
}

function renderGeneroChart(genero) {
    if (chartGenero) chartGenero.destroy();

    document.getElementById('val-hombres').textContent = formatNum(genero.hombres);
    document.getElementById('val-mujeres').textContent = formatNum(genero.mujeres);

    const ctx = document.getElementById('chart-genero').getContext('2d');
    chartGenero = new Chart(ctx, {
        type: 'pie',
        data: {
            labels: ['HOMBRES', 'MUJERES'],
            datasets: [{
                data: [genero.hombres, genero.mujeres],
                backgroundColor: ['#0d3629', '#691c32'],
                borderWidth: 2,
                borderColor: '#ffffff'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            layout: {
                padding: { top: 4, bottom: 4, left: 4, right: 4 }
            },
            plugins: {
                legend: { display: false },
                datalabels: {
                    color: '#ffffff',
                    font: { weight: 'bold', size: 11 },
                    formatter: (value, ctx) => {
                        const sum = ctx.dataset.data.reduce((a, b) => a + b, 0);
                        const percentage = sum > 0 ? (value * 100 / sum).toFixed(2) + "%" : '0%';
                        return percentage;
                    }
                }
            }
        }
    });
}

function renderCultivosTable(cultivos, totalProd, totalSup) {
    const tbody = document.getElementById('cultivos-tbody');
    tbody.innerHTML = '';

    cultivos.forEach(c => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td style="text-align:left; font-weight:600;">${c.cultivo}</td>
            <td>${formatNum(c.derechohabientes)}</td>
            <td>${formatNum(c.superficie)}</td>
            <td>${c.porcentaje}</td>
        `;
        tbody.appendChild(tr);
    });

    document.getElementById('tbl-total-prod').textContent = formatNum(totalProd);
    document.getElementById('tbl-total-sup').textContent = formatNum(totalSup);
}

function renderEdadesChart(edades) {
    if (chartEdades) chartEdades.destroy();

    const labels = Object.keys(edades);
    const dataVals = Object.values(edades);

    const ctx = document.getElementById('chart-edades').getContext('2d');
    chartEdades = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                data: dataVals,
                borderColor: '#691c32',
                backgroundColor: '#691c32',
                borderWidth: 2,
                pointRadius: 4,
                fill: false,
                tension: 0.2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            layout: {
                padding: { top: 25, bottom: 5, left: 10, right: 10 }
            },
            plugins: {
                legend: { display: false },
                datalabels: {
                    align: 'top',
                    offset: 4,
                    color: '#1a1a1a',
                    font: { weight: 'bold', size: 9 },
                    formatter: (v) => v > 0 ? formatNum(v) : ''
                }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { font: { size: 9, weight: 'bold' } }
                },
                y: {
                    display: false,
                    beginAtZero: true,
                    grace: '20%'
                }
            }
        }
    });
}

function renderEntregasChart(sdata) {
    if (chartEntregas) chartEntregas.destroy();

    const entregasMes = sdata.entregas_mes || [];
    const labels = entregasMes.map(m => m.mes);
    const pointsData = entregasMes.map(m => m.conteo);

    const ctx = document.getElementById('chart-entregas').getContext('2d');
    chartEntregas = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Entregas',
                data: pointsData,
                borderColor: '#0d3629',
                backgroundColor: '#0d3629',
                borderWidth: 2.5,
                pointRadius: 5,
                fill: false,
                tension: 0.2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            layout: {
                padding: { top: 25, bottom: 5, left: 20, right: 20 }
            },
            plugins: {
                legend: { display: false },
                datalabels: {
                    align: 'top',
                    offset: 4,
                    color: '#111111',
                    font: { weight: 'bold', size: 10 },
                    formatter: (v) => v > 0 ? formatNum(v) : ''
                }
            },
            scales: {
                x: {
                    grid: { color: '#e5ded0' },
                    ticks: { font: { size: 10, weight: 'bold' } }
                },
                y: {
                    display: false,
                    beginAtZero: true,
                    grace: '20%'
                }
            }
        }
    });
}

// PDF Export Handler: Expands table completely during capture, then restores web view
function exportToPDF() {
    const reportPaper = document.querySelector('.report-paper');
    const tableContainer = document.querySelector('.table-container');
    
    // Temporarily expand table for PDF capture
    if (tableContainer) tableContainer.classList.add('pdf-mode');

    const widthPx = reportPaper.offsetWidth || 1170;
    const heightPx = reportPaper.offsetHeight || 1200;
    
    const pdfWidthPt = widthPx * 0.75;
    const pdfHeightPt = heightPx * 0.75 + 12;

    const opt = {
        margin:       [0, 0, 0, 0],
        filename:     `Informe_Fertilizantes_${currentState}_${selectedDate}.pdf`,
        image:        { type: 'jpeg', quality: 0.98 },
        html2canvas:  { 
            scale: 2, 
            useCORS: true, 
            logging: false,
            scrollX: 0,
            scrollY: 0
        },
        jsPDF:        { unit: 'pt', format: [pdfWidthPt, pdfHeightPt], orientation: 'portrait' },
        pagebreak:    { mode: [] }
    };

    html2pdf().set(opt).from(reportPaper).save().then(() => {
        // Restore web view
        if (tableContainer) tableContainer.classList.remove('pdf-mode');
    }).catch(err => {
        console.error('PDF Export error:', err);
        if (tableContainer) tableContainer.classList.remove('pdf-mode');
    });
}

// Utility Formatting Functions
function formatNum(val) {
    if (val === undefined || val === null) return '0';
    return Number(val).toLocaleString('es-MX');
}

function formatDec(val, decimals = 2) {
    if (val === undefined || val === null) return '0.00';
    return Number(val).toLocaleString('es-MX', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function formatFechaMexican(dateStr) {
    if (!dateStr || dateStr.length < 10) return dateStr || '';
    const parts = dateStr.split('-');
    if (parts.length === 3) {
        return `${parts[2]}/${parts[1]}/${parts[0]}`;
    }
    return dateStr;
}
