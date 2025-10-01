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
            if (chartConfig) {
                new Chart(ctx, chartConfig);
            }
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
        const data = [
            Number(avgPhotoProcessingTime),
            Number(avgVideoProcessingTime),
            Number(avgUploadTime),
            Number(avgDownloadTime),
        ].map((value) => (value === 0 ? 0.1 : value));
        return {
            type: 'bar',
            data: {
                labels: ['Photo Processing', 'Video Processing', 'Upload', 'Download'],
                datasets: [{
                    label: 'Avg Seconds',
                    data,
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
                        type: 'logarithmic',
                        min: 0.1,
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

    createChartFromCanvas('source-acceptance', (dataset) => {
        const sourcesRaw = dataset.sources ? JSON.parse(dataset.sources) : [];
        if (sourcesRaw.length === 0) {
            return null;
        }
        const labels = sourcesRaw.map((entry) => entry.source);
        const acceptanceRates = sourcesRaw.map((entry) => Number(entry.acceptance_rate || 0));
        return {
            type: 'bar',
            data: {
                labels,
                datasets: [{
                    label: 'Acceptance %',
                    data: acceptanceRates,
                    backgroundColor: '#0d6efd',
                }],
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                scales: {
                    x: {
                        beginAtZero: true,
                        max: 100,
                    },
                },
                plugins: {
                    tooltip: {
                        callbacks: {
                            afterBody: (items) => {
                                if (!items.length) {
                                    return [];
                                }
                                const idx = items[0].dataIndex;
                                const entry = sourcesRaw[idx];
                                return [
                                    `Submissions: ${entry.submissions}`,
                                    `Approved: ${entry.approved}`,
                                    `Rejected: ${entry.rejected}`,
                                ];
                            },
                        },
                    },
                    legend: {
                        display: false,
                    },
                },
            },
        };
    });

    createChartFromCanvas('processing-histogram', (dataset) => {
        const histogram = dataset.histogram ? JSON.parse(dataset.histogram) : {};
        const photoBuckets = histogram.photo || [];
        const videoBuckets = histogram.video || [];
        const labels = photoBuckets.length
            ? photoBuckets.map((entry) => entry.label)
            : videoBuckets.map((entry) => entry.label);
        if (!labels.length) {
            return null;
        }
        const photoCounts = labels.map((label) => {
            const match = photoBuckets.find((entry) => entry.label === label);
            return match ? Number(match.count) : 0;
        });
        const videoCounts = labels.map((label) => {
            const match = videoBuckets.find((entry) => entry.label === label);
            return match ? Number(match.count) : 0;
        });
        return {
            type: 'bar',
            data: {
                labels,
                datasets: [
                    {
                        label: 'Photos',
                        data: photoCounts,
                        backgroundColor: '#0d6efd',
                    },
                    {
                        label: 'Videos',
                        data: videoCounts,
                        backgroundColor: '#6610f2',
                    },
                ],
            },
            options: {
                responsive: true,
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            stepSize: 1,
                            callback: (value) => (Number.isInteger(value) ? value : null),
                        },
                    },
                },
            },
        };
    });

    createChartFromCanvas('daily-post-counts', (dataset) => {
        const postsRaw = dataset.posts ? JSON.parse(dataset.posts) : [];
        if (!postsRaw.length) {
            return null;
        }
        const labels = postsRaw.map((entry) => entry.date);
        const counts = postsRaw.map((entry) => Number(entry.count || 0));
        return {
            type: 'line',
            data: {
                labels,
                datasets: [{
                    label: 'Posts',
                    data: counts,
                    borderColor: '#198754',
                    backgroundColor: 'rgba(25, 135, 84, 0.2)',
                    tension: 0.3,
                    fill: true,
                }],
            },
            options: {
                responsive: true,
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            stepSize: 1,
                            callback: (value) => (Number.isInteger(value) ? value : null),
                        },
                    },
                },
                plugins: {
                    legend: {
                        display: false,
                    },
                },
            },
        };
    });
})();
