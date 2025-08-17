import datetime
import logging
import os
from collections import defaultdict

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    create_engine,
    func,
)
from sqlalchemy.orm import declarative_base, sessionmaker

from telegram_auto_poster.utils.db import (
    _redis_key,
    _redis_meta_key,
    get_redis_client,
)
from telegram_auto_poster.utils.timezone import UTC, now_utc

Base = declarative_base()


class StatsCounter(Base):
    """SQLAlchemy model representing a named counter.

    Attributes:
        id (int): Primary key.
        scope (str): Counter namespace such as ``"daily"`` or ``"total"``.
        name (str): Human readable metric name.
        value (int): Current value of the counter.
    """

    __tablename__ = "stats_counters"
    id = Column(Integer, primary_key=True)
    scope = Column(String(10), nullable=False)  # 'daily' or 'total'
    name = Column(String(50), nullable=False)
    value = Column(Integer, default=0, nullable=False)


class Metadata(Base):
    """Simple key/value storage for miscellaneous metadata.

    Attributes:
        key (str): Metadata identifier.
        value (str): Stored metadata value.
    """

    __tablename__ = "metadata"
    key = Column(String(50), primary_key=True)
    value = Column(String(100), nullable=False)


class History(Base):
    """Model for storing individual history events.

    Each row represents a noteworthy event such as a processing error,
    approval or download.

    Attributes:
        id (int): Primary key.
        category (str): Event category (e.g. ``"approval"``).
        timestamp (datetime): Time of the event.
        filename (str | None): Related file name, if any.
        source (str | None): Origin of the event such as a channel name.
        duration (float | None): Processing duration for time based events.
        error_type (str | None): Specific error type for error events.
        message (str | None): Optional description or error message.
        media_type (str | None): Media type associated with the event.
    """

    __tablename__ = "history"
    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String(50), nullable=False)
    timestamp = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    filename = Column(String(200))
    source = Column(String(50))
    duration = Column(Float)
    error_type = Column(String(50))
    message = Column(Text)
    media_type = Column(String(50))


# Database connection
user = os.getenv("DB_MYSQL_USER")
password = os.getenv("DB_MYSQL_PASSWORD")
host = os.getenv("DB_MYSQL_HOST", "localhost")
port = os.getenv("DB_MYSQL_PORT", "3306")
dbname = os.getenv("DB_MYSQL_NAME")
DATABASE_URL = f"mysql+pymysql://{user}:{password}@{host}:{port}/{dbname}"


class MediaStats:
    """High level interface for collecting and retrieving statistics.

    The class keeps counters in both MySQL and Valkey and exposes helper
    methods for recording events and generating reports.

    Attributes:
        db (Session): SQLAlchemy session used for persistent storage.
        r (Any): Valkey (Redis compatible) client instance.
        names (list[str]): List of known counter names used by the bot.
    """

    _instance = None

    def __new__(cls):
        print("Creating a new MediaStats instance")
        if cls._instance is None:
            cls._instance = super(MediaStats, cls).__new__(cls)
            cls._instance.db = SessionLocal()
            cls._instance.r = get_redis_client()
            cls._instance._init_db()
        return cls._instance

    def _init_db(self):
        """Populate the database and cache with initial counter values."""
        names = [
            "media_received",
            "media_processed",
            "photos_received",
            "videos_received",
            "photos_processed",
            "videos_processed",
            "photos_approved",
            "videos_approved",
            "photos_rejected",
            "videos_rejected",
            "photos_added_to_batch",
            "videos_added_to_batch",
            "batch_sent",
            "processing_errors",
            "storage_errors",
            "telegram_errors",
            "list_operations",
        ]
        self.names = names
        for scope in ("daily", "total"):
            for name in names:
                row = (
                    self.db.query(StatsCounter)
                    .filter_by(scope=scope, name=name)
                    .first()
                )
                if not row:
                    self.db.add(StatsCounter(scope=scope, name=name, value=0))
                    value = 0
                else:
                    value = row.value
                self.r.setnx(_redis_key(scope, name), value)
        # ensure daily reset metadata exists
        meta = self.db.query(Metadata).filter_by(key="daily_last_reset").first()
        if not meta:
            now = now_utc().isoformat()
            self.db.add(Metadata(key="daily_last_reset", value=now))
            self.r.set(_redis_meta_key(), now)
        else:
            self.r.setnx(_redis_meta_key(), meta.value)
        self.db.commit()

    def _increment(self, name: str, scope: str = "daily", count: int = 1) -> None:
        """Increment a named counter in both the database and Valkey.

        Args:
            name: Counter name to increase.
            scope: Counter scope, typically ``"daily"`` or ``"total"``.
            count: Amount to increment by.
        """
        stat = self.db.query(StatsCounter).filter_by(scope=scope, name=name).first()
        stat.value += count
        self.db.commit()
        # update valkey counters
        try:
            self.r.incrby(_redis_key(scope, name), count)
        except Exception:  # pragma: no cover - log and continue
            logging.exception("Failed to update Valkey counter %s:%s", scope, name)

    def record_received(self, media_type: str) -> None:
        """Record that a media item was received from a user.

        Args:
            media_type: Type of media, either ``"photo"`` or ``"video"``.
        """
        self._increment("media_received")
        self._increment("media_received", scope="total")
        if media_type == "photo":
            self._increment("photos_received")
            self._increment("photos_received", scope="total")
        elif media_type == "video":
            self._increment("videos_received")
            self._increment("videos_received", scope="total")

    def record_processed(self, media_type: str, processing_time: float) -> None:
        """Record completion of media processing and store its duration.

        Args:
            media_type: Processed media type (``"photo"`` or ``"video"``).
            processing_time: Time taken to process the media in seconds.
        """
        self._increment("media_processed")
        self._increment("media_processed", scope="total")
        category = f"{media_type}_processing"
        hist = History(
            category=category,
            timestamp=now_utc(),
            duration=processing_time,
        )
        self.db.add(hist)
        if media_type == "photo":
            self._increment("photos_processed")
            self._increment("photos_processed", scope="total")
        elif media_type == "video":
            self._increment("videos_processed")
            self._increment("videos_processed", scope="total")
        self.db.commit()

    def record_approved(
        self,
        media_type: str,
        filename: str | None = None,
        source: str | None = None,
    ) -> None:
        """Record that a piece of media passed moderation.

        Args:
            media_type: Approved media type.
            filename: Optional name of the associated file.
            source: Optional origin of the media.
        """
        name = "photos_approved" if media_type == "photo" else "videos_approved"
        self._increment(name)
        self._increment(name, scope="total")
        hist = History(
            category="approval",
            timestamp=now_utc(),
            media_type=media_type,
            filename=filename,
            source=source,
        )
        self.db.add(hist)
        self.db.commit()

    def record_rejected(
        self,
        media_type: str,
        filename: str | None = None,
        source: str | None = None,
    ) -> None:
        """Record that a piece of media failed moderation.

        Args:
            media_type: Rejected media type.
            filename: Optional name of the associated file.
            source: Optional origin of the media.
        """
        name = "photos_rejected" if media_type == "photo" else "videos_rejected"
        self._increment(name)
        self._increment(name, scope="total")
        hist = History(
            category="rejection",
            timestamp=now_utc(),
            media_type=media_type,
            filename=filename,
            source=source,
        )
        self.db.add(hist)
        self.db.commit()

    def record_added_to_batch(self, media_type: str) -> None:
        """Record that media was staged for later batch posting.

        Args:
            media_type: Type of media being queued for a batch.
        """
        name = (
            "photos_added_to_batch"
            if media_type == "photo"
            else "videos_added_to_batch"
        )
        self._increment(name)
        self._increment(name, scope="total")

    def record_batch_sent(self, count: int) -> None:
        """Record that a batch of media items was sent to the channel.

        Args:
            count: Number of media items included in the batch.
        """
        self._increment("batch_sent", count=count)
        self._increment("batch_sent", scope="total", count=count)

    def record_error(self, error_type: str, error_message: str) -> None:
        """Record an operational error and increment the relevant counter.

        Args:
            error_type: Category of error (``"processing"``, ``"storage"`` or
                ``"telegram"``).
            error_message: Human readable error description.
        """
        if error_type == "processing":
            name = "processing_errors"
        elif error_type == "storage":
            name = "storage_errors"
        else:
            name = "telegram_errors"
        self._increment(name)
        self._increment(name, scope="total")
        hist = History(
            category="error",
            timestamp=now_utc(),
            error_type=error_type,
            message=error_message,
        )
        self.db.add(hist)
        self.db.commit()

    def record_storage_operation(self, operation_type: str, duration: float) -> None:
        """Record how long a storage operation took to complete.

        Args:
            operation_type: Type of storage operation (``"upload"``,
                ``"download"`` or ``"list"``).
            duration: Time the operation took in seconds.
        """
        if operation_type not in ("upload", "download", "list"):
            return
        hist = History(
            category=operation_type,
            timestamp=now_utc(),
            duration=duration,
        )
        self.db.add(hist)
        if operation_type == "list":
            self._increment("list_operations")
            self._increment("list_operations", scope="total")
        self.db.commit()

    def get_daily_stats(self, reset_if_new_day: bool = True) -> dict:
        """Return a mapping of counters for the last 24 hours.

        Args:
            reset_if_new_day: Reset counters if the stored reset timestamp is
                from a previous day.

        Returns:
            dict: Mapping of counter names to values for the last day.
        """
        meta = self.db.query(Metadata).filter_by(key="daily_last_reset").first()
        last_reset = (
            lambda dt: dt.replace(tzinfo=UTC)
            if dt.tzinfo is None
            else dt.astimezone(UTC)
        )(datetime.datetime.fromisoformat(meta.value) if isinstance(meta.value, str) else now_utc())

        now = now_utc()
        if reset_if_new_day and last_reset.date() < now.date():
            # reset daily stats
            self.db.query(StatsCounter).filter_by(scope="daily").update(
                {StatsCounter.value: 0}
            )
            meta.value = now.isoformat()
            self.db.commit()
            for name in self.names:
                self.r.set(_redis_key("daily", name), 0)
            self.r.set(_redis_meta_key(), meta.value)
        stats = {}
        for name in self.names:
            value = self.r.get(_redis_key("daily", name))
            if value is None:
                row = (
                    self.db.query(StatsCounter)
                    .filter_by(scope="daily", name=name)
                    .first()
                )
                if row:
                    value = row.value
                    self.r.set(_redis_key("daily", name), value)
                else:
                    value = 0
            stats[name] = int(value)

        last_reset = self.r.get(_redis_meta_key())
        if last_reset is None:
            last_reset = meta.value
            self.r.set(_redis_meta_key(), last_reset)
        stats["last_reset"] = last_reset
        return stats

    def get_total_stats(self) -> dict:
        """Return cumulative counter values for the lifetime of the bot.

        Returns:
            dict: Mapping of counter names to total values.
        """
        stats = {}
        for name in self.names:
            value = self.r.get(_redis_key("total", name))
            if value is None:
                row = (
                    self.db.query(StatsCounter)
                    .filter_by(scope="total", name=name)
                    .first()
                )
                if row:
                    value = row.value
                    self.r.set(_redis_key("total", name), value)
                else:
                    value = 0
            stats[name] = int(value)
        return stats

    def get_performance_metrics(self) -> dict:
        """Return average processing, upload and download times.

        Returns:
            dict: Mapping of metric names to average durations in seconds.
        """
        pm = {}
        pm["avg_photo_processing_time"] = (
            self.db.query(func.avg(History.duration))
            .filter(History.category == "photo_processing")
            .scalar()
            or 0
        )
        pm["avg_video_processing_time"] = (
            self.db.query(func.avg(History.duration))
            .filter(History.category == "video_processing")
            .scalar()
            or 0
        )
        pm["avg_upload_time"] = (
            self.db.query(func.avg(History.duration))
            .filter(History.category == "upload")
            .scalar()
            or 0
        )
        pm["avg_download_time"] = (
            self.db.query(func.avg(History.duration))
            .filter(History.category == "download")
            .scalar()
            or 0
        )
        return pm

    def get_recent_errors(self, limit: int = 10) -> list[dict]:
        """Return a list of the most recent error events.

        Args:
            limit: Maximum number of events to return.

        Returns:
            list[dict]: Error records sorted newest first.
        """
        rows = (
            self.db.query(History)
            .filter_by(category="error")
            .order_by(History.timestamp.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "timestamp": r.timestamp.isoformat(),
                "type": r.error_type,
                "message": r.message,
            }
            for r in rows
        ]

    def get_recent_events(self, event_type: str, limit: int = 10) -> list[dict]:
        """Fetch recent events of a specific category.

        Args:
            event_type: Name of the event group to retrieve.
            limit: Maximum number of events to return.

        Returns:
            list[dict]: Event records sorted newest first.
        """
        mapping = {
            "photo_processing_times": "photo_processing",
            "video_processing_times": "video_processing",
            "upload_times": "upload",
            "download_times": "download",
            "errors": "error",
            "approvals": "approval",
            "rejections": "rejection",
        }
        category = mapping.get(event_type)
        if not category:
            return []
        rows = (
            self.db.query(History)
            .filter_by(category=category)
            .order_by(History.timestamp.desc())
            .limit(limit)
            .all()
        )
        events = []
        for r in rows:
            ev = {"timestamp": r.timestamp.isoformat()}
            if r.duration is not None:
                ev["duration"] = r.duration
            if r.media_type:
                ev["media_type"] = r.media_type
            if r.error_type:
                ev["type"] = r.error_type
                ev["message"] = r.message
            events.append(ev)
        return events

    def get_approval_rate_24h(self, daily: dict) -> float:
        """Calculate approval percentage for the last day.

        Args:
            daily: Mapping of daily counters as returned by
                :meth:`get_daily_stats`.

        Returns:
            float: Approval percentage in the range 0..100.
        """
        processed = daily["photos_processed"] + daily["videos_processed"]
        approved = daily["photos_approved"] + daily["videos_approved"]
        return (approved / processed * 100) if processed else 0

    def get_approval_rate_total(self) -> float:
        """Calculate overall approval percentage for all time.

        Returns:
            float: Approval percentage in the range 0..100.
        """
        ts = self.get_total_stats()
        processed = ts["photos_processed"] + ts["videos_processed"]
        approved = ts["photos_approved"] + ts["videos_approved"]
        return (approved / processed * 100) if processed else 0

    def get_success_rate_24h(self, daily: dict) -> float:
        """Compute success rate excluding errors for the last day.

        Args:
            daily: Mapping of daily counters as returned by
                :meth:`get_daily_stats`.

        Returns:
            float: Success percentage in the range 0..100.
        """
        received = daily["media_received"]
        errors = (
            daily["processing_errors"]
            + daily["storage_errors"]
            + daily["telegram_errors"]
        )
        return ((received - errors) / received * 100) if received else 100

    def get_busiest_hour(self) -> tuple[int | None, int]:
        """Return the hour with the most approvals or rejections in 24h.

        Returns:
            tuple[int | None, int]: Hour of day (0-23) and event count. ``None``
            is returned when there were no events.
        """
        now = now_utc()
        yesterday = now - datetime.timedelta(days=1)
        rows = (
            self.db.query(History)
            .filter(
                History.category.in_(["approval", "rejection"]),
                History.timestamp >= yesterday,
            )
            .all()
        )

        hour_counts = defaultdict(int)
        for r in rows:
            hour = r.timestamp.hour
            hour_counts[hour] += 1
        if not hour_counts:
            return None, 0
        busiest_hour, count = max(hour_counts.items(), key=lambda x: x[1])
        return busiest_hour, count

    def generate_stats_report(self, reset_daily: bool = True) -> str:
        """Create a human readable HTML report with recent statistics.

        Args:
            reset_daily: Whether to reset daily counters when generating the
                report.

        Returns:
            str: HTML snippet with formatted statistics.
        """
        daily = self.get_daily_stats(reset_if_new_day=reset_daily)
        total = self.get_total_stats()
        perf = self.get_performance_metrics()
        approval_24h = self.get_approval_rate_24h(daily)
        approval_total = self.get_approval_rate_total()
        success_24h = self.get_success_rate_24h(daily)
        busiest = self.get_busiest_hour()
        busiest_hour, count = busiest if busiest else (None, 0)
        busiest_display = (
            f"{busiest_hour}:00-{busiest_hour + 1}:00"
            if busiest_hour is not None
            else "N/A"
        )

        # Helper for formatting lines
        def format_line(icon, title, value, extra=""):
            return f"{icon} <b>{title}:</b> {value} {extra}".strip()

        report_sections = {
            "header": "📊 <b>Statistics Report</b> 📊",
            "daily": [
                "<b>Last 24 Hours:</b>",
                format_line("📥", "Media Received", daily.get("media_received", 0)),
                format_line("🖼️", "Photos Processed", daily.get("photos_processed", 0)),
                format_line("📹", "Videos Processed", daily.get("videos_processed", 0)),
                format_line(
                    "✅",
                    "Approved",
                    f"{daily.get('photos_approved', 0)} photos, {daily.get('videos_approved', 0)} videos",
                ),
                format_line(
                    "❌",
                    "Rejected",
                    f"{daily.get('photos_rejected', 0)} photos, {daily.get('videos_rejected', 0)} videos",
                ),
                format_line("📦", "Batches Sent", daily.get("batch_sent", 0)),
                format_line("📈", "Approval Rate", f"{approval_24h:.1f}%"),
                format_line("✨", "Success Rate", f"{success_24h:.1f}%"),
                format_line("🕔", "Busiest Hour", busiest_display, f"({count} events)"),
            ],
            "performance": [
                "<b>Performance Metrics:</b>",
                format_line(
                    "⏳",
                    "Avg Photo Processing",
                    f"{perf.get('avg_photo_processing_time', 0):.2f}s",
                ),
                format_line(
                    "⏳",
                    "Avg Video Processing",
                    f"{perf.get('avg_video_processing_time', 0):.2f}s",
                ),
                format_line(
                    "⏱️", "Avg Upload Time", f"{perf.get('avg_upload_time', 0):.2f}s"
                ),
                format_line(
                    "⏱️", "Avg Download Time", f"{perf.get('avg_download_time', 0):.2f}s"
                ),
            ],
            "total": [
                "<b>All-Time Totals:</b>",
                format_line("🗃️", "Media Processed", total.get("media_processed", 0)),
                format_line("🖼️", "Photos Approved", total.get("photos_approved", 0)),
                format_line("📹", "Videos Approved", total.get("videos_approved", 0)),
                format_line("📈", "Overall Approval Rate", f"{approval_total:.1f}%"),
                format_line("📦", "Total Batches Sent", total.get("batch_sent", 0)),
                format_line(
                    "🛑",
                    "Total Errors",
                    total.get("processing_errors", 0)
                    + total.get("storage_errors", 0)
                    + total.get("telegram_errors", 0),
                ),
            ],
            "footer": [f"<i>Last reset: {daily.get('last_reset', '')}</i>"],
        }

        # Build the report string
        report_parts = [
            report_sections["header"],
            "\n".join(report_sections["daily"]),
            "\n".join(report_sections["performance"]),
            "\n".join(report_sections["total"]),
            "\n".join(report_sections["footer"]),
        ]
        return "\n\n".join(report_parts)

    def reset_daily_stats(self) -> str:
        """Reset all daily counters and update the reset timestamp.

        Returns:
            str: Confirmation message describing the reset.
        """
        now_iso = now_utc().isoformat()
        self.db.query(StatsCounter).filter_by(scope="daily").update(
            {StatsCounter.value: 0}
        )
        meta = self.db.query(Metadata).filter_by(key="daily_last_reset").first()
        meta.value = now_iso
        self.db.commit()
        for name in self.names:
            self.r.set(_redis_key("daily", name), 0)
        self.r.set(_redis_meta_key(), now_iso)
        return "Daily statistics have been reset."

    def force_save(self) -> None:
        """Persist any outstanding database transactions."""
        self.db.commit()


engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)
Base.metadata.create_all(bind=engine)
stats = MediaStats()
