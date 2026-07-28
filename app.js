// Fertilizantes para el Bienestar 2026 - Dashboard App Logic

let globalData = {};
let currentState = 'NACIONAL'; // Default to NACIONAL
let selectedDate = '2026-07-27';

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
        ? 'Entregas Nacional 2026'
        : `Entregas en ${currentState} 2026`;
    document.getElementById('banner-title').textContent = titleText;

    // Pick max date if available
    const dates = Object.keys(sdata.atenciones_por_fecha || {}).sort();
    const maxDate = dates.length > 0 ? dates[dates.length - 1] : selectedDate;
    document.getElementById('banner-subtitle').textContent = formatFechaMexican(maxDate);
    
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
    document.getElementById('val-dap').textContent = formatDec(sdata.avance.dap_entregada, 3);
    document.getElementById('val-urea').textContent = formatDec(sdata.avance.urea_entregada, 3);
    document.getElementById('val-ha').textContent = formatNum(sdata.avance.ha_atendidas);

    const totalProdEntregado = (sdata.avance.dap_entregada || 0) + (sdata.avance.urea_entregada || 0);
    document.getElementById('val-total-prod-entregado').textContent = formatDec(totalProdEntregado, 3);

    // Render Donut Charts
    renderDonutChart('chart-derechohabientes', sdata.avance.pct_derechohabientes, '#5a1727', (chart) => chartDerechohabientes = chart, chartDerechohabientes, 12);
    renderDonutChart('chart-dap', sdata.avance.pct_dap, '#8c1d35', (chart) => chartDap = chart, chartDap, 11);
    renderDonutChart('chart-urea', sdata.avance.pct_urea, '#154e38', (chart) => chartUrea = chart, chartUrea, 11);
    renderDonutChart('chart-ha', sdata.avance.pct_ha, '#a37a2c', (chart) => chartHa = chart, chartHa, 12);

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
                    font: { weight: '800', size: 10 },
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
                    ticks: { font: { size: 10.5, weight: '800' }, color: '#000000', maxRotation: 45, autoSkip: false }
                },
                y: {
                    display: true,
                    beginAtZero: true,
                    grace: '18%',
                    grid: { color: '#e5ded0', drawBorder: false },
                    ticks: {
                        font: { size: 10, weight: '700' },
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

// FULLY ADAPTIVE PDF EXPORT HANDLER (Accurately measures unconstrained table height!)
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

        // 3. MEASURE REAL UNCONSTRAINED TABLE HEIGHT FROM .cultivos-table (35 crops = ~760px -> card ~840px, 10 crops = ~260px -> card ~340px)
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

        // 4. Render ADAPTIVE VERTICAL BAR CHART for Gender in PDF!
        const sdata = globalData[currentState] || {};
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
                            font: { weight: '800', size: matchedHeight < 500 ? 14 : 16 },
                            formatter: (v, ctx) => {
                                const pct = ctx.dataIndex === 0 ? pctH : pctM;
                                return `${formatNum(v)}\n(${pct}%)`;
                            }
                        }
                    },
                    scales: {
                        x: { 
                            ticks: { font: { size: matchedHeight < 500 ? 14 : 17, weight: '800' }, color: '#000000' }, 
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
                            font: { weight: '800', size: matchedHeight < 500 ? 10 : 11.5 },
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
                            ticks: { font: { size: matchedHeight < 500 ? 10.5 : 12, weight: '800' }, color: '#000000', maxRotation: 45, autoSkip: false }
                        },
                        y: {
                            display: true,
                            beginAtZero: true,
                            grace: '18%',
                            grid: { color: '#e5ded0', drawBorder: false },
                            ticks: {
                                font: { size: matchedHeight < 500 ? 9.5 : 11, weight: '700' },
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

        // Copy remaining canvases (Metas, Donut, Entregas) at High Resolution (2x scale)
        const origCanvases = [
            document.getElementById('chart-derechohabientes'),
            document.getElementById('chart-dap'),
            document.getElementById('chart-urea'),
            document.getElementById('chart-ha'),
            document.getElementById('chart-entregas')
        ];

        const cloneCanvases = [
            clone.querySelector('#chart-derechohabientes'),
            clone.querySelector('#chart-dap'),
            clone.querySelector('#chart-urea'),
            clone.querySelector('#chart-ha'),
            clone.querySelector('#chart-entregas')
        ];

        origCanvases.forEach((origCanvas, idx) => {
            if (origCanvas && cloneCanvases[idx]) {
                const destCtx = cloneCanvases[idx].getContext('2d');
                cloneCanvases[idx].width = origCanvas.width * 2;
                cloneCanvases[idx].height = origCanvas.height * 2;
                destCtx.scale(2, 2);
                destCtx.drawImage(origCanvas, 0, 0);
            }
        });

        const widthPx = 1200;
        const heightPx = clone.offsetHeight || 1400;

        const pdfWidthPt = widthPx * 0.75;
        const pdfHeightPt = heightPx * 0.75;

        const opt = {
            margin:       [0, 0, 0, 0],
            filename:     `Informe_Fertilizantes_${currentState}_${selectedDate}.pdf`,
            image:        { type: 'jpeg', quality: 1.0 },
            html2canvas:  { 
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
            jsPDF:        { unit: 'pt', format: [pdfWidthPt, pdfHeightPt], orientation: 'portrait', compress: true },
            pagebreak:    { mode: [] }
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
