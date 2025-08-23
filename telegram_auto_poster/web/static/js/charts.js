// Wrap in IIFE to avoid global redeclaration on repeated loads
(() => {
    // Only proceed if Chart.js is available
    if (typeof window.Chart === 'undefined') {
        // Silently skip initialization if Chart is not loaded
        return;
    }

    const dailyCanvas = document.getElementById('daily-activity');
    if (dailyCanvas) {
        const dailyCtx = dailyCanvas.getContext('2d');
        const {
            photosApproved,
            videosApproved,
            photosRejected,
            videosRejected,
        } = dailyCanvas.dataset;
        new Chart(dailyCtx, {
            type: 'bar',
            data: {
                labels: ['Photos Approved', 'Videos Approved', 'Photos Rejected', 'Videos Rejected'],
                datasets: [{
                    label: 'Last 24h',
                    data: [
                        Number(photosApproved),
                        Number(videosApproved),
                        Number(photosRejected),
                        Number(videosRejected),
                    ],
                    backgroundColor: ['#198754', '#198754', '#dc3545', '#dc3545'],
                }],
            },
            options: {
                responsive: true,
                plugins: {
                    legend: { display: false },
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            stepSize: 1,
                            callback: (value) => Number.isInteger(value) ? value : null,
                        }
                    }
                }
            },
        });
    }

    const errorCanvas = document.getElementById('error-breakdown');
    if (errorCanvas) {
        const errorCtx = errorCanvas.getContext('2d');
        const {
            processingErrors,
            storageErrors,
            telegramErrors,
        } = errorCanvas.dataset;
        new Chart(errorCtx, {
            type: 'bar',
            data: {
                labels: ['Processing', 'Storage', 'Telegram'],
                datasets: [{
                    data: [
                        Number(processingErrors),
                        Number(storageErrors),
                        Number(telegramErrors),
                    ],
                    backgroundColor: ['#ffc107', '#0dcaf0', '#6610f2'],
                }],
            },
            options: {
                responsive: true,
                plugins: {
                    legend: { display: false },
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            stepSize: 1,
                            callback: (value) => Number.isInteger(value) ? value : null,
                        }
                    }
                }
            },
        });
    }
})();
