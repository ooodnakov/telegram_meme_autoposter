import time
import datetime
import json
import os
from collections import defaultdict, deque
from threading import RLock
from loguru import logger

# Constants
STATS_FILE = "media_stats.json"
MAX_HISTORY_ITEMS = 1000  # Maximum number of items to keep in history


class MediaStats:
    """Class for tracking and managing media processing statistics"""

    _instance = None
    _lock = RLock()

    def __new__(cls):
        """Singleton pattern to ensure only one instance exists"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(MediaStats, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        """Initialize the stats tracking system"""
        if self._initialized:
            return

        self._last_save_time = time.time()
        self._save_interval = 300  # Save stats every 5 minutes
        self._initialized = True

        # Daily counters (reset every 24h)
        self.daily_stats = {
            "media_received": 0,
            "media_processed": 0,
            "photos_received": 0,
            "videos_received": 0,
            "photos_processed": 0,
            "videos_processed": 0,
            "photos_approved": 0,
            "videos_approved": 0,
            "photos_rejected": 0,
            "videos_rejected": 0,
            "photos_added_to_batch": 0,
            "videos_added_to_batch": 0,
            "batch_sent": 0,
            "processing_errors": 0,
            "storage_errors": 0,
            "telegram_errors": 0,
            "last_reset": datetime.datetime.now().isoformat(),
        }

        # Total counters (never reset)
        self.total_stats = {
            "media_received": 0,
            "media_processed": 0,
            "photos_received": 0,
            "videos_received": 0,
            "photos_processed": 0,
            "videos_processed": 0,
            "photos_approved": 0,
            "videos_approved": 0,
            "photos_rejected": 0,
            "videos_rejected": 0,
            "photos_added_to_batch": 0,
            "videos_added_to_batch": 0,
            "batch_sent": 0,
            "processing_errors": 0,
            "storage_errors": 0,
            "telegram_errors": 0,
        }

        # Performance metrics
        self.performance = {
            "avg_photo_processing_time": 0,
            "avg_video_processing_time": 0,
            "avg_upload_time": 0,
            "avg_download_time": 0,
        }

        # Detailed history for analysis
        self.history = {
            "photo_processing_times": deque(maxlen=MAX_HISTORY_ITEMS),
            "video_processing_times": deque(maxlen=MAX_HISTORY_ITEMS),
            "upload_times": deque(maxlen=MAX_HISTORY_ITEMS),
            "download_times": deque(maxlen=MAX_HISTORY_ITEMS),
            "errors": deque(maxlen=MAX_HISTORY_ITEMS),
            "approvals": deque(maxlen=MAX_HISTORY_ITEMS),
            "rejections": deque(maxlen=MAX_HISTORY_ITEMS),
        }

        # Load existing stats if available
        self._load_stats()

        # Check if we need to reset daily stats (if last reset was yesterday)
        self._check_daily_reset()

    def _load_stats(self):
        """Load stats from file if it exists"""
        try:
            if os.path.exists(STATS_FILE):
                with open(STATS_FILE, "r") as f:
                    data = json.load(f)

                # Load main stats counters
                if "daily_stats" in data:
                    self.daily_stats = data["daily_stats"]
                if "total_stats" in data:
                    self.total_stats = data["total_stats"]
                if "performance" in data:
                    self.performance = data["performance"]

                # Convert history items back to deque (they're stored as lists in JSON)
                if "history" in data:
                    for key, items in data["history"].items():
                        self.history[key] = deque(items, maxlen=MAX_HISTORY_ITEMS)

                logger.info("Statistics loaded from file")
        except Exception as e:
            logger.error(f"Error loading stats: {e}")

    def _save_stats(self, force=False):
        """Save stats to file, but only at certain intervals unless forced"""
        current_time = time.time()
        if force or (current_time - self._last_save_time > self._save_interval):
            try:
                # Convert deque to list for JSON serialization
                history_dict = {key: list(items) for key, items in self.history.items()}

                data = {
                    "daily_stats": self.daily_stats,
                    "total_stats": self.total_stats,
                    "performance": self.performance,
                    "history": history_dict,
                }

                with open(STATS_FILE, "w") as f:
                    json.dump(data, f, indent=2)

                self._last_save_time = current_time
                logger.debug("Statistics saved to file")
            except Exception as e:
                logger.error(f"Error saving stats: {e}")

    def _check_daily_reset(self):
        """Check if we need to reset daily stats"""
        try:
            last_reset = datetime.datetime.fromisoformat(self.daily_stats["last_reset"])
            now = datetime.datetime.now()

            # If the last reset was yesterday or earlier, reset daily stats
            if last_reset.date() < now.date():
                logger.info("Resetting daily statistics")
                for key in self.daily_stats:
                    if key != "last_reset":
                        self.daily_stats[key] = 0
                self.daily_stats["last_reset"] = now.isoformat()
        except Exception as e:
            logger.error(f"Error checking daily reset: {e}")
            # Reset the date if there was an error
            self.daily_stats["last_reset"] = datetime.datetime.now().isoformat()

    def record_received(self, media_type):
        """Record that media was received"""
        with self._lock:
            self.daily_stats["media_received"] += 1
            self.total_stats["media_received"] += 1

            if media_type == "photo":
                self.daily_stats["photos_received"] += 1
                self.total_stats["photos_received"] += 1
            elif media_type == "video":
                self.daily_stats["videos_received"] += 1
                self.total_stats["videos_received"] += 1

            self._save_stats()

    def record_processed(self, media_type, processing_time):
        """Record that media was processed"""
        with self._lock:
            self.daily_stats["media_processed"] += 1
            self.total_stats["media_processed"] += 1

            if media_type == "photo":
                self.daily_stats["photos_processed"] += 1
                self.total_stats["photos_processed"] += 1
                self.history["photo_processing_times"].append(
                    {
                        "timestamp": datetime.datetime.now().isoformat(),
                        "duration": processing_time,
                    }
                )

                # Update average processing time
                times = [
                    item["duration"] for item in self.history["photo_processing_times"]
                ]
                if times:
                    self.performance["avg_photo_processing_time"] = sum(times) / len(
                        times
                    )

            elif media_type == "video":
                self.daily_stats["videos_processed"] += 1
                self.total_stats["videos_processed"] += 1
                self.history["video_processing_times"].append(
                    {
                        "timestamp": datetime.datetime.now().isoformat(),
                        "duration": processing_time,
                    }
                )

                # Update average processing time
                times = [
                    item["duration"] for item in self.history["video_processing_times"]
                ]
                if times:
                    self.performance["avg_video_processing_time"] = sum(times) / len(
                        times
                    )

            self._save_stats()

    def record_approved(self, media_type):
        """Record that media was approved"""
        with self._lock:
            if media_type == "photo":
                self.daily_stats["photos_approved"] += 1
                self.total_stats["photos_approved"] += 1
            elif media_type == "video":
                self.daily_stats["videos_approved"] += 1
                self.total_stats["videos_approved"] += 1

            self.history["approvals"].append(
                {
                    "timestamp": datetime.datetime.now().isoformat(),
                    "media_type": media_type,
                }
            )

            self._save_stats()

    def record_rejected(self, media_type):
        """Record that media was rejected"""
        with self._lock:
            if media_type == "photo":
                self.daily_stats["photos_rejected"] += 1
                self.total_stats["photos_rejected"] += 1
            elif media_type == "video":
                self.daily_stats["videos_rejected"] += 1
                self.total_stats["videos_rejected"] += 1

            self.history["rejections"].append(
                {
                    "timestamp": datetime.datetime.now().isoformat(),
                    "media_type": media_type,
                }
            )

            self._save_stats()

    def record_added_to_batch(self, media_type):
        """Record that media was added to batch"""
        with self._lock:
            if media_type == "photo":
                self.daily_stats["photos_added_to_batch"] += 1
                self.total_stats["photos_added_to_batch"] += 1
            elif media_type == "video":
                self.daily_stats["videos_added_to_batch"] += 1
                self.total_stats["videos_added_to_batch"] += 1

            self._save_stats()

    def record_batch_sent(self, count):
        """Record that a batch was sent"""
        with self._lock:
            self.daily_stats["batch_sent"] += 1
            self.total_stats["batch_sent"] += 1
            self._save_stats()

    def record_error(self, error_type, error_message):
        """Record an error"""
        with self._lock:
            if error_type == "processing":
                self.daily_stats["processing_errors"] += 1
                self.total_stats["processing_errors"] += 1
            elif error_type == "storage":
                self.daily_stats["storage_errors"] += 1
                self.total_stats["storage_errors"] += 1
            elif error_type == "telegram":
                self.daily_stats["telegram_errors"] += 1
                self.total_stats["telegram_errors"] += 1

            self.history["errors"].append(
                {
                    "timestamp": datetime.datetime.now().isoformat(),
                    "type": error_type,
                    "message": error_message,
                }
            )

            self._save_stats()

    def record_storage_operation(self, operation_type, duration):
        """Record storage operation time (upload/download)"""
        with self._lock:
            if operation_type == "upload":
                self.history["upload_times"].append(
                    {
                        "timestamp": datetime.datetime.now().isoformat(),
                        "duration": duration,
                    }
                )

                # Update average upload time
                times = [item["duration"] for item in self.history["upload_times"]]
                if times:
                    self.performance["avg_upload_time"] = sum(times) / len(times)

            elif operation_type == "download":
                self.history["download_times"].append(
                    {
                        "timestamp": datetime.datetime.now().isoformat(),
                        "duration": duration,
                    }
                )

                # Update average download time
                times = [item["duration"] for item in self.history["download_times"]]
                if times:
                    self.performance["avg_download_time"] = sum(times) / len(times)

            self._save_stats()

    def get_daily_stats(self):
        """Get daily stats summary"""
        with self._lock:
            # Check if we need to reset first
            self._check_daily_reset()
            return dict(self.daily_stats)

    def get_total_stats(self):
        """Get total stats summary"""
        with self._lock:
            return dict(self.total_stats)

    def get_performance_metrics(self):
        """Get performance metrics"""
        with self._lock:
            return dict(self.performance)

    def get_recent_errors(self, limit=10):
        """Get most recent errors"""
        with self._lock:
            return list(self.history["errors"])[-limit:]

    def get_recent_events(self, event_type, limit=10):
        """Get most recent events of specified type"""
        with self._lock:
            if event_type in self.history:
                return list(self.history[event_type])[-limit:]
            return []

    def get_approval_rate_24h(self):
        """Get approval rate for last 24 hours"""
        with self._lock:
            total_processed = (
                self.daily_stats["photos_processed"]
                + self.daily_stats["videos_processed"]
            )
            total_approved = (
                self.daily_stats["photos_approved"]
                + self.daily_stats["videos_approved"]
            )

            if total_processed == 0:
                return 0
            return (total_approved / total_processed) * 100

    def get_approval_rate_total(self):
        """Get all-time approval rate"""
        with self._lock:
            total_processed = (
                self.total_stats["photos_processed"]
                + self.total_stats["videos_processed"]
            )
            total_approved = (
                self.total_stats["photos_approved"]
                + self.total_stats["videos_approved"]
            )

            if total_processed == 0:
                return 0
            return (total_approved / total_processed) * 100

    def get_success_rate_24h(self):
        """Get success rate for last 24 hours"""
        with self._lock:
            total_received = self.daily_stats["media_received"]
            total_errors = (
                self.daily_stats["processing_errors"]
                + self.daily_stats["storage_errors"]
                + self.daily_stats["telegram_errors"]
            )

            if total_received == 0:
                return 100  # No errors if nothing was processed
            return ((total_received - total_errors) / total_received) * 100

    def get_busiest_hour(self):
        """Get the busiest hour in the last 24 hours"""
        # Combine all events to find busiest hour
        hour_counts = defaultdict(int)
        now = datetime.datetime.now()
        yesterday = now - datetime.timedelta(days=1)

        for history_type in ["approvals", "rejections"]:
            for event in self.history[history_type]:
                try:
                    timestamp = datetime.datetime.fromisoformat(event["timestamp"])
                    if timestamp >= yesterday:
                        hour = timestamp.hour
                        hour_counts[hour] += 1
                except (ValueError, KeyError):
                    continue

        if not hour_counts:
            return None, 0

        busiest_hour, count = max(hour_counts.items(), key=lambda x: x[1])
        return busiest_hour, count

    def generate_stats_report(self):
        """Generate a comprehensive stats report"""
        with self._lock:
            logger.info("Generating stats report")
            # Check if we need to reset first
            self._check_daily_reset()

            # Calculate approval rates
            approval_rate_24h = self.get_approval_rate_24h()
            approval_rate_total = self.get_approval_rate_total()

            # Calculate success rates
            success_rate_24h = self.get_success_rate_24h()

            # Find busiest hour
            busiest_hour, count = self.get_busiest_hour() or (None, 0)
            busiest_hour_display = (
                f"{busiest_hour}:00-{busiest_hour + 1}:00"
                if busiest_hour is not None
                else "N/A"
            )

            report = [
                "📊 Statistics Report 📊",
                "",
                "📈 Last 24 Hours:",
                f"• Media Received: {self.daily_stats['media_received']}",
                f"• Photos Processed: {self.daily_stats['photos_processed']}",
                f"• Videos Processed: {self.daily_stats['videos_processed']}",
                f"• Photos Approved: {self.daily_stats['photos_approved']}",
                f"• Videos Approved: {self.daily_stats['videos_approved']}",
                f"• Photos Rejected: {self.daily_stats['photos_rejected']}",
                f"• Videos Rejected: {self.daily_stats['videos_rejected']}",
                f"• Batches Sent: {self.daily_stats['batch_sent']}",
                f"• Approval Rate: {approval_rate_24h:.1f}%",
                f"• Success Rate: {success_rate_24h:.1f}%",
                f"• Busiest Hour: {busiest_hour_display} ({count} events)",
                "",
                "⏱️ Performance Metrics:",
                f"• Average Photo Processing: {self.performance['avg_photo_processing_time']:.2f}s",
                f"• Average Video Processing: {self.performance['avg_video_processing_time']:.2f}s",
                f"• Average Upload Time: {self.performance['avg_upload_time']:.2f}s",
                f"• Average Download Time: {self.performance['avg_download_time']:.2f}s",
                "",
                "🔢 All-Time Totals:",
                f"• Media Processed: {self.total_stats['media_processed']}",
                f"• Photos Approved: {self.total_stats['photos_approved']}",
                f"• Videos Approved: {self.total_stats['videos_approved']}",
                f"• Overall Approval Rate: {approval_rate_total:.1f}%",
                f"• Total Batches Sent: {self.total_stats['batch_sent']}",
                f"• Total Errors: {self.total_stats['processing_errors'] + self.total_stats['storage_errors'] + self.total_stats['telegram_errors']}",
                "",
                "Last reset: "
                + datetime.datetime.fromisoformat(
                    self.daily_stats["last_reset"]
                ).strftime("%Y-%m-%d %H:%M:%S"),
            ]

            return "\n".join(report)

    def reset_daily_stats(self):
        """Manually reset daily stats"""
        with self._lock:
            for key in self.daily_stats:
                if key != "last_reset":
                    self.daily_stats[key] = 0
            self.daily_stats["last_reset"] = datetime.datetime.now().isoformat()
            self._save_stats(force=True)
            return "Daily statistics have been reset."

    def force_save(self):
        """Force save stats to file"""
        with self._lock:
            self._save_stats(force=True)


# Create a global instance
stats = MediaStats()
