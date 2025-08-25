// Wrap in IIFE to avoid global redeclaration on repeated loads
(() => {
    // Only proceed if Chart.js is available
    if (typeof window.Chart === 'undefined') {
        // Silently skip initialization if Chart is not loaded
        return;
    }

    const createChartFromCanvas = (canvasId, chartConfigBuilder) => {
        const canvas = document.getElementById(canvasId);
        if (canvas) {
            const ctx = canvas.getContext('2d');
            const chartConfig = chartConfigBuilder(canvas.dataset);
            new Chart(ctx, chartConfig);
        }
    };

    createChartFromCanvas('daily-activity', (dataset) => {
        const {
            photosApproved,
            videosApproved,
            photosRejected,
            videosRejected,
        } = dataset;
        return {
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
        };
    });

    createChartFromCanvas('error-breakdown', (dataset) => {
        const {
            processingErrors,
            storageErrors,
            telegramErrors,
        } = dataset;
        return {
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
        };
    });

    createChartFromCanvas('performance-metrics', (dataset) => {
        const {
            avgPhotoProcessingTime,
            avgVideoProcessingTime,
            avgUploadTime,
            avgDownloadTime,
        } = dataset;
        return {
            type: 'bar',
            data: {
                labels: ['Photo Processing', 'Video Processing', 'Upload', 'Download'],
                datasets: [{
                    label: 'Avg Seconds',
                    data: [
                        Number(avgPhotoProcessingTime),
                        Number(avgVideoProcessingTime),
                        Number(avgUploadTime),
                        Number(avgDownloadTime),
                    ],
                    backgroundColor: ['#0d6efd', '#0d6efd', '#0dcaf0', '#0dcaf0'],
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
                    }
                }
            },
        };
    });

    createChartFromCanvas('total-activity', (dataset) => {
        const {
            photosApproved,
            videosApproved,
            photosRejected,
            videosRejected,
        } = dataset;
        const totalApproved = Number(photosApproved) + Number(videosApproved);
        const totalRejected = Number(photosRejected) + Number(videosRejected);
        return {
            type: 'pie',
            data: {
                labels: ['Approved', 'Rejected'],
                datasets: [{
                    data: [totalApproved, totalRejected],
                    backgroundColor: ['#198754', '#dc3545'],
                }],
            },
            options: {
                responsive: true,
            },
        };
    });
})();
