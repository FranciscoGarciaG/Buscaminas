function getTodayYYYYMMDD() {
    const d = new Date();
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

let globalData = {};
let currentState = 'NACIONAL'; // Default to NACIONAL
let selectedDate = getTodayYYYYMMDD();

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
        const fontSize = chart.config.options.plugins.centerText.fontSize || 13;

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
    const datePicker = document.getElementById('date-picker');
    if (datePicker) {
        datePicker.value = selectedDate;
        ['change', 'input'].forEach(evt => {
            datePicker.addEventListener(evt, (e) => {
                selectedDate = e.target.value;
                updateDateAtencion();
            });
        });
    }

    loadData();

    document.getElementById('state-select').addEventListener('change', (e) => {
        currentState = e.target.value;
        updateDashboard();
    });

    const btnPdf = document.getElementById('btn-export-pdf');
    if (btnPdf) {
        btnPdf.addEventListener('click', exportToPDF);
    }
});

async function loadData() {
    try {
        let resp;
        const antiCache = '?v=' + Date.now();
        try {
            resp = await fetch('/api/data' + antiCache);
            if (!resp.ok) throw new Error();
        } catch (e) {
            resp = await fetch('dashboard_data.json' + antiCache);
        }

        if (!resp.ok) throw new Error('Data file not found');
        globalData = await resp.json();

        populateStateDropdown();
        updateDashboard();

        const statusEl = document.getElementById('data-status');
        if (statusEl) statusEl.textContent = '🟢 Datos 2026 Cargados';
    } catch (err) {
        console.error('Error loading dataset:', err);
        const statusEl = document.getElementById('data-status');
        if (statusEl) {
            if (window.location.protocol === 'file:') {
                statusEl.textContent = '⚠️ Iniciar servidor http (doble clic en start_server.bat)';
            } else {
                statusEl.textContent = '⚠️ Error cargando datos (Pulse F5)';
            }
        }
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
    if (!currentState) currentState = 'NACIONAL';
    const sdata = globalData[currentState];
    if (!sdata) return;

    // 1. Banner Titles
    const titleText = currentState === 'NACIONAL'
        ? 'Entregas Nacional 2026'
        : `Entregas en ${currentState} 2026`;
    document.getElementById('banner-title').textContent = titleText;

    // Asegurar que el date-picker mantenga la fecha seleccionada (por defecto hoy)
    const dp = document.getElementById('date-picker');
    if (dp && dp.value !== selectedDate) {
        dp.value = selectedDate;
    }

    // 2. Metas Section
    document.getElementById('meta-derechohabientes').textContent = formatNum(sdata.meta.productores);
    const totalMetaFertilizante = (sdata.meta.dap_ton || 0) + (sdata.meta.urea_ton || 0);
    document.getElementById('meta-fertilizante').textContent = formatDec(totalMetaFertilizante, 3);
    document.getElementById('meta-hectareas').textContent = formatNum(sdata.meta.hectareas);

    // 3. Avance Section Values
    document.getElementById('val-dap').textContent = formatDec(sdata.avance.dap_entregada, 3);
    document.getElementById('val-urea').textContent = formatDec(sdata.avance.urea_entregada, 3);
    document.getElementById('val-ha').textContent = formatNum(sdata.avance.ha_atendidas);

    const totalProdEntregado = (sdata.avance.dap_entregada || 0) + (sdata.avance.urea_entregada || 0);
    document.getElementById('val-total-prod-entregado').textContent = formatDec(totalProdEntregado, 3);

    // Render Donut Charts para Fertilizante y Hectareas
    renderDonutChart('chart-dap', sdata.avance.pct_dap, '#8c1d35', (chart) => chartDap = chart, chartDap, 11);
    renderDonutChart('chart-urea', sdata.avance.pct_urea, '#154e38', (chart) => chartUrea = chart, chartUrea, 11);
    renderDonutChart('chart-ha', sdata.avance.pct_ha, '#a37a2c', (chart) => chartHa = chart, chartHa, 12);

    // Date Atencion (Actualiza Totales Atendidos acum, dona de avance, fecha de corte y diario)
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

    const dates = Object.keys(sdata.atenciones_por_fecha || {}).sort();
    const maxDate = dates.length > 0 ? dates[dates.length - 1] : selectedDate;

    // Calcular acumulado hasta la fecha seleccionada
    let cumulativeAtendidos = 0;
    if (dates.length > 0) {
        for (const dStr of dates) {
            if (dStr <= selectedDate) {
                cumulativeAtendidos += (sdata.atenciones_por_fecha[dStr] || 0);
            }
        }
    } else {
        cumulativeAtendidos = sdata.avance.atendidos || 0;
    }

    // Si la fecha seleccionada es mayor o igual al maximo de fechas, usar el acumulado total exacto del estado
    if (dates.length > 0 && selectedDate >= maxDate) {
        cumulativeAtendidos = sdata.avance.atendidos;
    }

    // Calcular el porcentaje de avance dinamico a la fecha seleccionada
    const metaProd = sdata.meta.productores || 0;
    const pctAtendidos = metaProd > 0 ? Number(((100.0 / metaProd) * cumulativeAtendidos).toFixed(2)) : 0;

    // Actualizar UI
    document.getElementById('val-atendidos').textContent = formatNum(cumulativeAtendidos);
    document.getElementById('banner-subtitle').textContent = formatFechaMexican(selectedDate);
    document.getElementById('label-fecha-atencion').textContent = formatFechaMexican(selectedDate);

    const lblTotal = document.getElementById('label-total-corte');
    if (lblTotal) {
        lblTotal.textContent = `Total a ${formatFechaMexican(selectedDate)}`;
    }

    const singleDayCount = sdata.atenciones_por_fecha[selectedDate] || 0;
    document.getElementById('val-atendidos-fecha').textContent = formatNum(singleDayCount);

    // Actualizar dona de porcentaje de Derechohabientes Atendidos a la fecha elegida
    renderDonutChart('chart-derechohabientes', pctAtendidos, '#5a1727', (chart) => chartDerechohabientes = chart, chartDerechohabientes, 12);
}

// Donut Chart Helper with padding to prevent clipping
function renderDonutChart(canvasId, pct, color, setRef, existingRef, fontSize = 12) {
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
            cutout: '72%',
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
                    color: '#1a1a1a',
                    fontSize: fontSize
                }
            }
        }
    });

    setRef(chart);
}

// Pie Chart for Gender (Web View)
function renderGeneroChart(genero) {
    if (chartGenero) chartGenero.destroy();

    document.getElementById('val-hombres').textContent = formatNum(genero.hombres);
    document.getElementById('val-mujeres').textContent = formatNum(genero.mujeres);

    const ctx = document.getElementById('chart-genero').getContext('2d');
    chartGenero = new Chart(ctx, {
        type: 'pie',
        data: {
            labels: ['Hombres', 'Mujeres'],
            datasets: [{
                data: [genero.hombres, genero.mujeres],
                backgroundColor: ['#154e38', '#691c32'],
                borderWidth: 2,
                borderColor: '#ffffff'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            layout: {
                padding: { top: 6, bottom: 6, left: 6, right: 6 }
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

// ADAPTIVE Age Segmentation Line Chart
function renderEdadesChart(edades) {
    if (chartEdades) chartEdades.destroy();

    const labels = Object.keys(edades);
    const dataVals = Object.values(edades);
    const maxVal = Math.max(...dataVals, 10);
    const useMil = maxVal >= 10000;

    const ctx = document.getElementById('chart-edades').getContext('2d');
    chartEdades = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                data: dataVals,
                borderColor: '#691c32',
                backgroundColor: '#691c32',
                borderWidth: 2.5,
                pointRadius: 4.5,
                fill: false,
                tension: 0.2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            layout: {
                padding: { top: 30, bottom: 25, left: 10, right: 25 }
            },
            plugins: {
                legend: { display: false },
                datalabels: {
                    align: (ctx) => {
                        if (ctx.dataIndex === 3) return 'left';
                        if (ctx.dataIndex === 4) return 'right';
                        if (ctx.dataIndex === 8) return 'right';
                        return 'top';
                    },
                    offset: 6,
                    color: '#000000',
                    font: { weight: '700', size: 9.5 },
                    formatter: (v) => {
                        if (v === 0) return '';
                        if (useMil && v >= 1000) {
                            return Math.round(v / 1000) + ' mil';
                        }
                        return formatNum(v);
                    }
                }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { font: { size: 9.5, weight: '700' }, color: '#000000', maxRotation: 45, autoSkip: false }
                },
                y: {
                    display: true,
                    beginAtZero: true,
                    grace: '18%',
                    grid: { color: '#e5ded0', drawBorder: false },
                    ticks: {
                        font: { size: 9, weight: '600' },
                        color: '#444444',
                        callback: (v) => {
                            if (useMil) {
                                if (v === 0) return '0 mil';
                                if (v >= 1000) return (v / 1000) + ' mil';
                                return v;
                            }
                            return formatNum(v);
                        }
                    }
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
                borderColor: '#154e38',
                backgroundColor: '#154e38',
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
                    font: { weight: '700', size: 10 },
                    formatter: (v) => v > 0 ? formatNum(v) : ''
                }
            },
            scales: {
                x: {
                    grid: { color: '#e5ded0' },
                    ticks: { font: { size: 10, weight: '700' }, color: '#000000' }
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

// Ultra High-Definition PDF Export Handler (100% PERFECT ON MOBILE & DESKTOP)
function exportToPDF() {
    const btnPdf = document.getElementById('btn-export-pdf');
    const originalText = btnPdf ? btnPdf.textContent : '📄 Descargar PDF';

    if (btnPdf) {
        btnPdf.disabled = true;
        btnPdf.textContent = '⏳ Generando PDF...';
    }

    try {
        const reportPaper = document.querySelector('.report-paper');
        if (!reportPaper) {
            if (btnPdf) {
                btnPdf.disabled = false;
                btnPdf.textContent = originalText;
            }
            return;
        }

        // 1. Create 1:1 clone
        const clone = reportPaper.cloneNode(true);

        // In clone, expand table container completely to show all crops + TOTAL row
        const cloneTableContainer = clone.querySelector('.table-container');
        if (cloneTableContainer) {
            cloneTableContainer.classList.add('pdf-mode');
            cloneTableContainer.style.height = 'auto';
            cloneTableContainer.style.maxHeight = 'none';
            cloneTableContainer.style.overflow = 'visible';
            cloneTableContainer.style.border = 'none';
        }

        const cloneCardCultivos = clone.querySelector('.card-cultivos');
        if (cloneCardCultivos) {
            cloneCardCultivos.style.height = 'auto';
            cloneCardCultivos.style.minHeight = 'auto';
            cloneCardCultivos.style.maxHeight = 'none';
            cloneCardCultivos.style.padding = '12px 14px';
        }

        // Un-sticky th headers in clone
        const cloneThs = clone.querySelectorAll('.cultivos-table th');
        cloneThs.forEach(th => th.style.position = 'static');

        // 2. Position clone at origin (0,0) behind main page
        const wrapper = document.createElement('div');
        wrapper.style.position = 'fixed';
        wrapper.style.left = '0px';
        wrapper.style.top = '0px';
        wrapper.style.width = '1200px';
        wrapper.style.zIndex = '-99999';
        wrapper.style.opacity = '0.01';
        wrapper.style.pointerEvents = 'none';
        wrapper.style.boxSizing = 'border-box';
        wrapper.classList.add('force-desktop-pdf');
        wrapper.appendChild(clone);
        document.body.appendChild(wrapper);

        // 3. MEASURE REAL UNCONSTRAINED TABLE HEIGHT FROM .cultivos-table
        const tableEl = clone.querySelector('.cultivos-table');
        const realTableHeight = tableEl ? tableEl.offsetHeight + 80 : (cloneCardCultivos ? cloneCardCultivos.scrollHeight : 360);
        const matchedHeight = Math.max(340, realTableHeight);
        const chartAreaHeight = matchedHeight - 50;

        // Force ALL 3 CARDS in clone to match that NATURAL ADAPTIVE height!
        const cloneSectionTri = clone.querySelector('.section-tri');
        if (cloneSectionTri) {
            cloneSectionTri.style.height = matchedHeight + 'px';
            cloneSectionTri.style.alignItems = 'stretch';
        }

        const cloneCardGenero = clone.querySelector('.card-genero');
        if (cloneCardGenero) {
            cloneCardGenero.style.height = matchedHeight + 'px';
            cloneCardGenero.style.minHeight = matchedHeight + 'px';
            cloneCardGenero.style.maxHeight = matchedHeight + 'px';
            cloneCardGenero.style.padding = '12px 14px';

            const cloneLegend = cloneCardGenero.querySelector('.genero-legend');
            if (cloneLegend) cloneLegend.style.display = 'none';

            const clonePieContainer = cloneCardGenero.querySelector('.pie-chart-container');
            if (clonePieContainer) {
                clonePieContainer.style.height = chartAreaHeight + 'px';
                clonePieContainer.style.maxHeight = chartAreaHeight + 'px';
                clonePieContainer.style.margin = 'auto 0';
                clonePieContainer.style.flex = '1 1 auto';
            }
        }

        const cloneCardEdades = clone.querySelector('.card-edades');
        if (cloneCardEdades) {
            cloneCardEdades.style.height = matchedHeight + 'px';
            cloneCardEdades.style.minHeight = matchedHeight + 'px';
            cloneCardEdades.style.maxHeight = matchedHeight + 'px';
            cloneCardEdades.style.padding = '12px 14px';

            const cloneLineContainer = cloneCardEdades.querySelector('.line-chart-container');
            if (cloneLineContainer) {
                cloneLineContainer.style.height = chartAreaHeight + 'px';
                cloneLineContainer.style.maxHeight = chartAreaHeight + 'px';
                cloneLineContainer.style.margin = 'auto 0';
                cloneLineContainer.style.flex = '1 1 auto';
            }
        }

        if (cloneCardCultivos) {
            cloneCardCultivos.style.height = matchedHeight + 'px';
            cloneCardCultivos.style.minHeight = matchedHeight + 'px';
            cloneCardCultivos.style.maxHeight = matchedHeight + 'px';
        }

        const sdata = globalData[currentState] || {};

        // 4. Render ADAPTIVE VERTICAL BAR CHART for Gender in PDF!
        const genero = sdata.genero || { hombres: 0, mujeres: 0 };
        const hVal = genero.hombres || 0;
        const mVal = genero.mujeres || 0;
        const totalGen = hVal + mVal;
        const pctH = totalGen > 0 ? ((hVal * 100) / totalGen).toFixed(2) : '0';
        const pctM = totalGen > 0 ? ((mVal * 100) / totalGen).toFixed(2) : '0';

        const cloneGeneroCanvas = cloneCardGenero ? cloneCardGenero.querySelector('canvas') : null;
        if (cloneGeneroCanvas) {
            cloneGeneroCanvas.width = 560;
            cloneGeneroCanvas.height = chartAreaHeight * 2;

            const barThicknessPx = matchedHeight < 500 ? 70 : 100;

            new Chart(cloneGeneroCanvas.getContext('2d'), {
                type: 'bar',
                data: {
                    labels: ['Hombres', 'Mujeres'],
                    datasets: [{
                        data: [hVal, mVal],
                        backgroundColor: ['#154e38', '#691c32'],
                        borderRadius: 10,
                        barThickness: barThicknessPx
                    }]
                },
                options: {
                    indexAxis: 'x',
                    responsive: false,
                    maintainAspectRatio: false,
                    animation: false,
                    layout: {
                        padding: { top: 35, bottom: 20, left: 15, right: 15 }
                    },
                    plugins: {
                        legend: { display: false },
                        datalabels: {
                            anchor: 'end',
                            align: 'top',
                            color: '#000000',
                            font: { weight: '800', size: matchedHeight < 500 ? 24 : 28 },
                            formatter: (v, ctx) => {
                                const pct = ctx.dataIndex === 0 ? pctH : pctM;
                                return `${formatNum(v)}\n(${pct}%)`;
                            }
                        }
                    },
                    scales: {
                        x: {
                            ticks: { font: { size: matchedHeight < 500 ? 24 : 28, weight: '800' }, color: '#000000' },
                            grid: { display: false }
                        },
                        y: {
                            display: false,
                            beginAtZero: true,
                            grace: '15%'
                        }
                    }
                }
            });
        }

        // 5. Render ADAPTIVE AGE LINE CHART directly on clone canvas
        const cloneEdadesCanvas = cloneCardEdades ? cloneCardEdades.querySelector('canvas') : null;
        if (cloneEdadesCanvas) {
            const edades = sdata.edades || {};
            const labels = Object.keys(edades);
            const dataVals = Object.values(edades);
            const maxVal = Math.max(...dataVals, 10);
            const useMil = maxVal >= 10000;

            cloneEdadesCanvas.width = 560;
            cloneEdadesCanvas.height = chartAreaHeight * 2;

            new Chart(cloneEdadesCanvas.getContext('2d'), {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [{
                        data: dataVals,
                        borderColor: '#691c32',
                        backgroundColor: '#691c32',
                        borderWidth: 2.8,
                        pointRadius: 5,
                        fill: false,
                        tension: 0.2
                    }]
                },
                options: {
                    responsive: false,
                    maintainAspectRatio: false,
                    animation: false,
                    layout: {
                        padding: { top: 30, bottom: 20, left: 10, right: 25 }
                    },
                    plugins: {
                        legend: { display: false },
                        datalabels: {
                            align: (ctx) => {
                                if (ctx.dataIndex === 3) return 'left';
                                if (ctx.dataIndex === 4) return 'right';
                                if (ctx.dataIndex === 8) return 'right';
                                return 'top';
                            },
                            offset: 6,
                            color: '#000000',
                            font: { weight: '800', size: matchedHeight < 500 ? 20 : 24 },
                            formatter: (v) => {
                                if (v === 0) return '';
                                if (useMil && v >= 1000) {
                                    return Math.round(v / 1000) + ' mil';
                                }
                                return formatNum(v);
                            }
                        }
                    },
                    scales: {
                        x: {
                            grid: { display: false },
                            ticks: { font: { size: matchedHeight < 500 ? 20 : 22, weight: '800' }, color: '#000000', maxRotation: 45, autoSkip: false }
                        },
                        y: {
                            display: true,
                            beginAtZero: true,
                            grace: '18%',
                            grid: { color: '#e5ded0', drawBorder: false },
                            ticks: {
                                font: { size: matchedHeight < 500 ? 16 : 18, weight: '800' },
                                color: '#444444',
                                callback: (v) => {
                                    if (useMil) {
                                        if (v === 0) return '0 mil';
                                        if (v >= 1000) return (v / 1000) + ' mil';
                                        return v;
                                    }
                                    return formatNum(v);
                                }
                            }
                        }
                    }
                }
            });
        }

        // 6. RE-RENDER ENTREGAS MENSUALES DIRECTLY ON CLONE CANVAS (100% Full Width on Phones & Mobile!)
        const cloneEntregasCanvas = clone.querySelector('#chart-entregas');
        if (cloneEntregasCanvas) {
            const entregasMes = sdata.entregas_mes || [];
            const labels = entregasMes.map(m => m.mes);
            const pointsData = entregasMes.map(m => m.conteo);

            const cloneEntregasContainer = clone.querySelector('.entregas-chart-container');
            if (cloneEntregasContainer) {
                cloneEntregasContainer.style.height = '240px';
                cloneEntregasContainer.style.width = '100%';
            }

            cloneEntregasCanvas.width = 2300; // 1150px * 2 for ultra high resolution
            cloneEntregasCanvas.height = 480;  // 240px * 2
            cloneEntregasCanvas.style.width = '100%';
            cloneEntregasCanvas.style.height = '240px';

            new Chart(cloneEntregasCanvas.getContext('2d'), {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Entregas',
                        data: pointsData,
                        borderColor: '#154e38',
                        backgroundColor: '#154e38',
                        borderWidth: 3,
                        pointRadius: 6,
                        fill: false,
                        tension: 0.2
                    }]
                },
                options: {
                    responsive: false,
                    maintainAspectRatio: false,
                    animation: false,
                    layout: {
                        padding: { top: 30, bottom: 10, left: 30, right: 30 }
                    },
                    plugins: {
                        legend: { display: false },
                        datalabels: {
                            align: 'top',
                            offset: 8,
                            color: '#111111',
                            font: { weight: '800', size: 28 },
                            formatter: (v) => v > 0 ? formatNum(v) : ''
                        }
                    },
                    scales: {
                        x: {
                            grid: { color: '#e5ded0' },
                            ticks: { font: { size: 26, weight: '800' }, color: '#000000' }
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

        // Copy remaining small Donut canvases at High Resolution (2x scale)
        const origDonuts = [
            document.getElementById('chart-derechohabientes'),
            document.getElementById('chart-dap'),
            document.getElementById('chart-urea'),
            document.getElementById('chart-ha')
        ];

        const cloneDonuts = [
            clone.querySelector('#chart-derechohabientes'),
            clone.querySelector('#chart-dap'),
            clone.querySelector('#chart-urea'),
            clone.querySelector('#chart-ha')
        ];

        origDonuts.forEach((origCanvas, idx) => {
            if (origCanvas && cloneDonuts[idx]) {
                const destCtx = cloneDonuts[idx].getContext('2d');
                cloneDonuts[idx].width = origCanvas.width * 2;
                cloneDonuts[idx].height = origCanvas.height * 2;
                destCtx.scale(2, 2);
                destCtx.drawImage(origCanvas, 0, 0);
            }
        });

        const widthPx = 1200;
        const heightPx = clone.offsetHeight || 1400;

        const pdfWidthPt = widthPx * 0.75;
        const pdfHeightPt = heightPx * 0.75;

        const opt = {
            margin: [0, 0, 0, 0],
            filename: `Informe_Fertilizantes_${currentState}_${selectedDate}.pdf`,
            image: { type: 'jpeg', quality: 1.0 },
            html2canvas: {
                scale: 3, // 300 DPI Retina High Definition capture
                useCORS: true,
                logging: false,
                x: 0,
                y: 0,
                width: widthPx,
                height: heightPx,
                scrollX: 0,
                scrollY: 0,
                windowWidth: widthPx
            },
            jsPDF: { unit: 'pt', format: [pdfWidthPt, pdfHeightPt], orientation: 'portrait', compress: true },
            pagebreak: { mode: [] }
        };

        html2pdf().set(opt).from(clone).save().then(() => {
            if (wrapper.parentNode) document.body.removeChild(wrapper);
            if (btnPdf) {
                btnPdf.disabled = false;
                btnPdf.textContent = originalText;
            }
        }).catch(err => {
            console.error('PDF Export error:', err);
            if (wrapper.parentNode) document.body.removeChild(wrapper);
            if (btnPdf) {
                btnPdf.disabled = false;
                btnPdf.textContent = originalText;
            }
        });
    } catch (err) {
        console.error('PDF Generation exception:', err);
        if (btnPdf) {
            btnPdf.disabled = false;
            btnPdf.textContent = originalText;
        }
    }
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

let selectedCSVFiles = [];
let isUpdating = false;

function openUpdateModal() {
    const modal = document.getElementById('update-modal');
    if (modal) {
        modal.style.display = 'flex';
        document.getElementById('update-login-section').style.display = 'block';
        document.getElementById('update-progress-section').style.display = 'none';

        const dropzone = document.getElementById('csv-dropzone');
        const uploadBtn = document.getElementById('btn-upload-csvs');

        if (dropzone) dropzone.style.display = 'block';
        if (uploadBtn) {
            uploadBtn.style.display = 'inline-block';
            uploadBtn.disabled = selectedCSVFiles.length === 0;
        }

        setupDragAndDrop();
    }
}

async function uploadCSVFiles() {
    if (selectedCSVFiles.length === 0) {
        alert('Por favor seleccione al menos un archivo CSV.');
        return;
    }

    isUpdating = true;

    // Switch to progress view
    document.getElementById('update-login-section').style.display = 'none';
    document.getElementById('update-progress-section').style.display = 'block';

    const logEl = document.getElementById('update-log');
    if (logEl) logEl.innerHTML = '';

    updateProgressBar(15, 'Subiendo archivos...');
    addLogEntry(`📤 Subiendo ${selectedCSVFiles.length} reporte(s) CSV al servidor...`, 'info');

    const formData = new FormData();
    selectedCSVFiles.forEach(file => {
        formData.append('files', file);
    });

    try {
        updateProgressBar(40, 'Procesando datos...');
        addLogEntry('⚙️ Ejecutando consolidación y cálculo de datos con process_data.py...', 'info');

        const resp = await fetch('/api/upload-csvs', {
            method: 'POST',
            body: formData
        });

        if (resp.ok) {
            const data = await resp.json();
            updateProgressBar(90, 'Completado');
            addLogEntry(`✅ ${data.message}`, 'success');

            addLogEntry('🔄 Actualizando vista del dashboard...', 'info');
            setTimeout(() => {
                reloadDashboardData();
            }, 1000);
        } else {
            const err = await resp.json().catch(() => ({}));
            updateProgressBar(0, 'Error');
            addLogEntry(`❌ Error en servidor: ${err.detail || 'Fallo al procesar los archivos.'}`, 'error');
            isUpdating = false;
        }
    } catch (e) {
        updateProgressBar(0, 'Error');
        addLogEntry(`❌ Error de conexión al servidor: ${e.message}`, 'error');
        isUpdating = false;
    }
}

function tryLocalStorageGet(key) {
    try { return localStorage.getItem(key); } catch (e) { return null; }
}

function closeUpdateModal() {
    const modal = document.getElementById('update-modal');
    if (modal) modal.style.display = 'none';
}

function setupDragAndDrop() {
    const dropzone = document.getElementById('csv-dropzone');
    if (!dropzone || dropzone.dataset.initialized) return;

    dropzone.dataset.initialized = 'true';

    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropzone.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    ['dragenter', 'dragover'].forEach(eventName => {
        dropzone.addEventListener(eventName, () => dropzone.classList.add('dragover'), false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropzone.addEventListener(eventName, () => dropzone.classList.remove('dragover'), false);
    });

    dropzone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files && files.length > 0) {
            processFilesArray(Array.from(files));
        }
    }, false);
}

function handleCSVFileSelection(event) {
    const files = event.target.files;
    if (files && files.length > 0) {
        processFilesArray(Array.from(files));
    }
}

function processFilesArray(files) {
    const csvFiles = files.filter(f => f.name.toLowerCase().endsWith('.csv') || f.name.toLowerCase().includes('.csv'));

    if (csvFiles.length === 0) {
        alert('Por favor seleccione únicamente archivos con formato .csv');
        return;
    }

    selectedCSVFiles = csvFiles;
    renderSelectedFilesList();
}

function renderSelectedFilesList() {
    const listEl = document.getElementById('csv-file-list');
    const uploadBtn = document.getElementById('btn-upload-csvs');

    if (!listEl) return;

    listEl.innerHTML = '';
    listEl.style.display = 'block';

    selectedCSVFiles.forEach(file => {
        const item = document.createElement('div');
        item.className = 'file-item';
        const sizeMb = (file.size / (1024 * 1024)).toFixed(2);
        item.innerHTML = `
            <span class="file-item-name">📄 ${file.name}</span>
            <span class="file-item-size">${sizeMb} MB</span>
        `;
        listEl.appendChild(item);
    });

    if (uploadBtn) {
        uploadBtn.disabled = selectedCSVFiles.length === 0;
        uploadBtn.textContent = `⚡ Procesar ${selectedCSVFiles.length} Reporte(s) CSV`;
    }
}

async function uploadCSVFiles() {
    if (selectedCSVFiles.length === 0) {
        alert('Seleccione al menos un archivo CSV.');
        return;
    }

    isUpdating = true;

    // Switch to progress view
    document.getElementById('update-login-section').style.display = 'none';
    document.getElementById('update-progress-section').style.display = 'block';

    const logEl = document.getElementById('update-log');
    if (logEl) logEl.innerHTML = '';

    updateProgressBar(10, 'Subiendo archivos...');
    addLogEntry(`📤 Subiendo ${selectedCSVFiles.length} archivos CSV al servidor...`, 'info');

    const formData = new FormData();
    selectedCSVFiles.forEach(file => {
        formData.append('files', file);
    });

    try {
        updateProgressBar(40, 'Procesando datos...');
        addLogEntry('⚙️ Ejecutando consolidación y cálculo de datos con process_data.py...', 'info');

        const resp = await fetch('/api/upload-csvs', {
            method: 'POST',
            body: formData
        });

        if (resp.ok) {
            const data = await resp.json();
            updateProgressBar(90, 'Completado');
            addLogEntry(`✅ ${data.message}`, 'success');

            addLogEntry('🔄 Actualizando vista del dashboard...', 'info');
            setTimeout(() => {
                reloadDashboardData();
            }, 1000);
        } else {
            const err = await resp.json().catch(() => ({}));
            updateProgressBar(0, 'Error');
            addLogEntry(`❌ Error en servidor: ${err.detail || 'Fallo al procesar los archivos.'}`, 'error');
            isUpdating = false;
        }
    } catch (e) {
        updateProgressBar(0, 'Error');
        addLogEntry(`❌ Error de conexión al servidor local: ${e.message}`, 'error');
        addLogEntry('💡 Asegúrese de ejecutar el servidor con start_server.bat', 'warning');
        isUpdating = false;
    }
}

function connectUpdateSSE() {
    if (updateEventSource) {
        updateEventSource.close();
    }

    updateEventSource = new EventSource('/api/events');

    updateEventSource.onmessage = function (event) {
        try {
            const data = JSON.parse(event.data);

            if (data.type === 'heartbeat' || data.type === 'connected') return;

            // Update progress bar
            if (data.progress !== undefined && data.progress > 0) {
                updateProgressBar(data.progress, data.step || '');
            }

            // Add log entry
            if (data.message) {
                addLogEntry(data.message, data.level || 'info');
            }

            // Update step label
            if (data.step) {
                updateStepLabel(data.step, data.message);
            }

            // Handle completion
            if (data.type === 'complete') {
                isUpdating = false;
                updateProgressBar(100, 'complete');
                document.getElementById('btn-stop-update').style.display = 'none';

                // Reload dashboard data
                addLogEntry('🔄 Recargando datos del dashboard...', 'info');
                setTimeout(() => {
                    reloadDashboardData();
                }, 1500);
            }

            // Handle errors
            if (data.level === 'error' && data.step === 'error') {
                isUpdating = false;
                document.getElementById('btn-stop-update').textContent = '← Volver';
                document.getElementById('btn-stop-update').onclick = function () {
                    document.getElementById('update-login-section').style.display = 'block';
                    document.getElementById('update-progress-section').style.display = 'none';
                    document.getElementById('btn-stop-update').textContent = '⛔ Detener';
                    document.getElementById('btn-stop-update').onclick = stopUpdate;
                    document.getElementById('btn-stop-update').style.display = 'block';
                };
            }
        } catch (e) {
            console.warn('SSE parse error:', e);
        }
    };

    updateEventSource.onerror = function () {
        // SSE connection lost, will auto-reconnect
        console.warn('SSE connection interrupted, reconnecting...');
    };
}

function updateProgressBar(percent, step) {
    const bar = document.getElementById('update-progress-bar');
    if (bar) {
        bar.style.width = percent + '%';
        bar.textContent = Math.round(percent) + '%';

        // Color transitions
        if (percent >= 100) {
            bar.style.background = 'linear-gradient(135deg, #154e38, #1a7a56)';
        } else if (percent >= 85) {
            bar.style.background = 'linear-gradient(135deg, #b58c3a, #c9aa63)';
        } else {
            bar.style.background = 'linear-gradient(135deg, #691c32, #8c2a45)';
        }
    }
}

function updateStepLabel(step, message) {
    const label = document.getElementById('update-step-label');
    if (!label) return;

    const stepLabels = {
        'start': '🚀 Iniciando...',
        'browser': '🌐 Navegador',
        'login': '🔐 Inicio de Sesión',
        'navigate': '📍 Navegación',
        'clean': '🧹 Limpieza',
        'download': '📥 Descargando Reportes',
        'download_complete': '📊 Descarga Finalizada',
        'processing': '⚙️ Procesando Datos',
        'processing_done': '✅ Datos Procesados',
        'complete': '🎉 ¡Actualización Completa!',
        'error': '❌ Error',
        'stopped': '⛔ Detenido',
    };

    label.textContent = stepLabels[step] || message || step;
}

function addLogEntry(message, level) {
    const logEl = document.getElementById('update-log');
    if (!logEl) return;

    const entry = document.createElement('div');
    entry.className = `log-entry log-${level}`;

    const time = new Date().toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    entry.innerHTML = `<span class="log-time">[${time}]</span> ${message}`;

    logEl.appendChild(entry);
    logEl.scrollTop = logEl.scrollHeight;
}

async function reloadDashboardData() {
    try {
        // Try fetching from server API first, fallback to direct file
        let resp;
        try {
            resp = await fetch('/api/data');
        } catch (e) {
            resp = await fetch('dashboard_data.json');
        }

        if (!resp.ok) throw new Error('Data reload failed');

        globalData = await resp.json();
        populateStateDropdown();
        updateDashboard();

        addLogEntry('✅ Dashboard actualizado con los nuevos datos.', 'success');
        document.getElementById('data-status').textContent = '🟢 Datos Actualizados';

        // Close modal after a delay
        setTimeout(() => {
            closeUpdateModal();
        }, 3000);
    } catch (e) {
        addLogEntry(`⚠️ Error recargando datos: ${e.message}`, 'warning');
    }
}
