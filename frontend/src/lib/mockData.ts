// Mock data for the dashboard demo

export const mockStats = {
  daily: {
    media_received: 47,
    photos_processed: 32,
    videos_processed: 15,
    photos_approved: 24,
    videos_approved: 11,
    photos_rejected: 8,
    videos_rejected: 4,
  },
  weekly: {
    media_received: 312,
    photos_processed: 215,
    videos_processed: 97,
    photos_approved: 178,
    videos_approved: 72,
    photos_rejected: 37,
    videos_rejected: 25,
  },
  monthly: {
    media_received: 1247,
    photos_processed: 856,
    videos_processed: 391,
    photos_approved: 698,
    videos_approved: 289,
    photos_rejected: 158,
    videos_rejected: 102,
  },
  total: {
    media_received: 8934,
    photos_processed: 6123,
    videos_processed: 2811,
    photos_approved: 5102,
    videos_approved: 2134,
    photos_rejected: 1021,
    videos_rejected: 677,
  },
};

export const mockQueueItems = [
  { id: 1, path: "photos/meme_001.jpg", caption: "When the code works on first try", ts: "2026-03-08 14:00", type: "image" as const },
  { id: 2, path: "videos/vid_042.mp4", caption: "Monday mood compilation", ts: "2026-03-08 16:00", type: "video" as const },
  { id: 3, path: "photos/meme_002.jpg", caption: "CSS centering struggle", ts: "2026-03-08 18:00", type: "image" as const },
  { id: 4, path: "photos/meme_003.jpg", caption: "Git merge conflicts be like", ts: "2026-03-08 20:00", type: "image" as const },
  { id: 5, path: "videos/vid_043.mp4", caption: "Production deploy at 5pm Friday", ts: "2026-03-09 10:00", type: "video" as const },
];

export const mockBatchItems = [
  { id: 1, path: "batch/img_101.jpg", caption: "Debugging in production", type: "image" as const, source: "@meme_channel_1" },
  { id: 2, path: "batch/img_102.jpg", caption: "Stack overflow saving lives", type: "image" as const, source: "@dev_memes" },
  { id: 3, path: "batch/vid_201.mp4", caption: "When the intern pushes to main", type: "video" as const, source: "@tech_humor" },
  { id: 4, path: "batch/img_103.jpg", caption: "Dark mode everything", type: "image" as const, source: "@meme_channel_1" },
  { id: 5, path: "batch/img_104.jpg", caption: "Recursion joke", type: "image" as const, source: "@dev_memes" },
  { id: 6, path: "batch/vid_202.mp4", caption: "Code review reactions", type: "video" as const, source: "@tech_humor" },
];

export const mockSuggestions = [
  { id: 1, path: "suggestions/sug_001.jpg", caption: "AI replacing developers", type: "image" as const, source: "user_42", submitted: "2026-03-08 10:23" },
  { id: 2, path: "suggestions/sug_002.jpg", caption: "Tabs vs spaces war", type: "image" as const, source: "user_17", submitted: "2026-03-08 11:45" },
  { id: 3, path: "suggestions/sug_003.mp4", caption: "Docker container escape", type: "video" as const, source: "user_88", submitted: "2026-03-08 12:10" },
];

export const mockPosts = [
  { id: 1, path: "posted/post_501.jpg", caption: "Monday motivation for devs", type: "image" as const, posted: "2026-03-07 14:00", views: 2341 },
  { id: 2, path: "posted/post_502.jpg", caption: "JavaScript quirks", type: "image" as const, posted: "2026-03-07 18:00", views: 5672 },
  { id: 3, path: "posted/post_503.mp4", caption: "Pair programming be like", type: "video" as const, posted: "2026-03-06 14:00", views: 8923 },
  { id: 4, path: "posted/post_504.jpg", caption: "Legacy code horror", type: "image" as const, posted: "2026-03-06 18:00", views: 3456 },
];

export const mockLeaderboard = {
  submissions: [
    { source: "@meme_channel_1", submissions: 145, approved: 112, rejected: 33, approved_pct: 77.2, rejected_pct: 22.8 },
    { source: "@dev_memes", submissions: 98, approved: 89, rejected: 9, approved_pct: 90.8, rejected_pct: 9.2 },
    { source: "@tech_humor", submissions: 67, approved: 45, rejected: 22, approved_pct: 67.2, rejected_pct: 32.8 },
    { source: "user_42", submissions: 34, approved: 28, rejected: 6, approved_pct: 82.4, rejected_pct: 17.6 },
    { source: "user_17", submissions: 21, approved: 15, rejected: 6, approved_pct: 71.4, rejected_pct: 28.6 },
  ],
  approved: [
    { source: "@meme_channel_1", submissions: 145, approved: 112, rejected: 33, approved_pct: 77.2, rejected_pct: 22.8 },
    { source: "@dev_memes", submissions: 98, approved: 89, rejected: 9, approved_pct: 90.8, rejected_pct: 9.2 },
    { source: "@tech_humor", submissions: 67, approved: 45, rejected: 22, approved_pct: 67.2, rejected_pct: 32.8 },
    { source: "user_42", submissions: 34, approved: 28, rejected: 6, approved_pct: 82.4, rejected_pct: 17.6 },
    { source: "user_17", submissions: 21, approved: 15, rejected: 6, approved_pct: 71.4, rejected_pct: 28.6 },
  ],
  rejected: [
    { source: "@meme_channel_1", submissions: 145, approved: 112, rejected: 33, approved_pct: 77.2, rejected_pct: 22.8 },
    { source: "@tech_humor", submissions: 67, approved: 45, rejected: 22, approved_pct: 67.2, rejected_pct: 32.8 },
    { source: "@dev_memes", submissions: 98, approved: 89, rejected: 9, approved_pct: 90.8, rejected_pct: 9.2 },
    { source: "user_42", submissions: 34, approved: 28, rejected: 6, approved_pct: 82.4, rejected_pct: 17.6 },
    { source: "user_17", submissions: 21, approved: 15, rejected: 6, approved_pct: 71.4, rejected_pct: 28.6 },
  ],
};

export const mockEvents = [
  { id: 1, type: "approved", message: "Photo meme_001.jpg approved and sent to channel", timestamp: "2026-03-08 13:45", source: "@meme_channel_1" },
  { id: 2, type: "rejected", message: "Photo sug_004.jpg rejected — duplicate content", timestamp: "2026-03-08 13:30", source: "user_42" },
  { id: 3, type: "scheduled", message: "Video vid_042.mp4 scheduled for 16:00", timestamp: "2026-03-08 13:15", source: "@tech_humor" },
  { id: 4, type: "received", message: "New media received: img_105.jpg", timestamp: "2026-03-08 13:00", source: "@dev_memes" },
  { id: 5, type: "approved", message: "Photo meme_003.jpg approved and queued", timestamp: "2026-03-08 12:45", source: "@meme_channel_1" },
  { id: 6, type: "batch_sent", message: "Batch of 5 items sent to channel", timestamp: "2026-03-08 12:30", source: "system" },
  { id: 7, type: "received", message: "New suggestion received: sug_003.mp4", timestamp: "2026-03-08 12:15", source: "user_88" },
  { id: 8, type: "approved", message: "Video vid_041.mp4 approved", timestamp: "2026-03-08 12:00", source: "@tech_humor" },
  { id: 9, type: "rejected", message: "Photo sug_005.jpg rejected — low quality", timestamp: "2026-03-08 11:45", source: "user_17" },
  { id: 10, type: "scheduled", message: "Photo meme_002.jpg scheduled for 18:00", timestamp: "2026-03-08 11:30", source: "@dev_memes" },
];

export const mockTrashItems = [
  { id: 1, path: "trash/del_001.jpg", caption: "Low quality meme", type: "image" as const, deleted: "2026-03-08 11:45", reason: "Low quality" },
  { id: 2, path: "trash/del_002.jpg", caption: "Duplicate content", type: "image" as const, deleted: "2026-03-08 10:30", reason: "Duplicate" },
  { id: 3, path: "trash/del_003.mp4", caption: "Copyright issue", type: "video" as const, deleted: "2026-03-07 16:20", reason: "Copyright" },
];

export const placeholderImages = [
  "https://images.unsplash.com/photo-1531297484001-80022131f5a1?w=400&h=400&fit=crop",
  "https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?w=400&h=400&fit=crop",
  "https://images.unsplash.com/photo-1550745165-9bc0b252726f?w=400&h=400&fit=crop",
  "https://images.unsplash.com/photo-1555949963-aa79dcee981c?w=400&h=400&fit=crop",
  "https://images.unsplash.com/photo-1461749280684-dccba630e2f6?w=400&h=400&fit=crop",
  "https://images.unsplash.com/photo-1504639725590-34d0984388bd?w=400&h=400&fit=crop",
];
