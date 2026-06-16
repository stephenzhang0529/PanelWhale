#!/usr/bin/env python3
"""Generate ~8 days of fake DeepSeek API usage data for testing.

Covers Mon 2026-06-01 through Fri 2026-06-12, with realistic usage patterns:
- Higher consumption during working hours (9–11am, 2–5pm peak)
- Lower on weekends
- Multiple sessions per day
"""

import os
import json
import random
from datetime import datetime, timedelta, timezone

random.seed(42)

LOCAL_TZ = datetime.now(timezone.utc).astimezone().tzinfo
LOG_DIR = os.path.expanduser("~/.local/share/panelwhale/logs")
os.makedirs(LOG_DIR, exist_ok=True)

START_DATE = datetime(2026, 6, 1, tzinfo=LOCAL_TZ)   # Monday
END_DATE   = datetime(2026, 6, 12, 23, 59, tzinfo=LOCAL_TZ)  # Friday

# Base hourly consumption pattern (relative weight)
# Peaks at 10am and 3pm, low at night
HOURLY_WEIGHT = [
    0.02, 0.01, 0.01, 0.01, 0.01, 0.02, 0.05,   # 0–6
    0.10, 0.25, 0.50, 0.60, 0.35, 0.40, 0.55,   # 7–13
    0.65, 0.70, 0.55, 0.45, 0.30, 0.20, 0.10,   # 14–20
    0.08, 0.05, 0.03, 0.02,                      # 21–23
]

def day_weight(dt: datetime) -> float:
    """Weekdays ~1.0, Saturday ~0.4, Sunday ~0.2."""
    wd = dt.weekday()
    if wd < 5:
        return 1.0
    if wd == 5:
        return 0.4
    return 0.2

def generate_sessions(day: datetime):
    """Generate 1–4 session logs for a given day."""
    num_sessions = random.choices([1, 2, 3, 4], weights=[2, 4, 3, 1])[0]
    sessions = []

    # Divide the day into sessions
    possible_starts = [7, 9, 13, 16, 20]  # typical session start hours
    chosen_starts = sorted(random.sample(possible_starts, min(num_sessions, len(possible_starts))))

    for start_hour in chosen_starts:
        session_start = day.replace(hour=start_hour, minute=random.randint(0, 30))
        duration_hours = random.uniform(0.5, 4.0)
        session_end = session_start + timedelta(hours=duration_hours)

        # Generate entries every 5 minutes during the session
        entries = []
        cursor = session_start
        balance = random.uniform(80.0, 120.0)  # starting balance for this session

        while cursor < session_end:
            hour_weight = HOURLY_WEIGHT[cursor.hour]
            base_consumption = random.uniform(0.0, 0.15) * hour_weight * day_weight(cursor)
            consumption = round(base_consumption, 6)

            balance -= consumption
            if balance < 0:
                balance += random.uniform(50, 100)  # top up

            entries.append({
                "ts": cursor.isoformat(timespec="seconds"),
                "consumption": consumption,
                "balance": round(balance, 2),
            })
            cursor += timedelta(minutes=5)

        if entries:
            sessions.append({
                "session_start": session_start.isoformat(timespec="seconds"),
                "entries": entries,
                "session_end": session_end.isoformat(timespec="seconds"),
                "sum_consumption": round(sum(e["consumption"] for e in entries), 6),
            })

    return sessions


def main():
    # Clean existing fake logs (only those matching our test date range)
    print("Cleaning old test logs …")
    for fname in os.listdir(LOG_DIR):
        if fname.endswith(".json") and fname[:10] >= "2026-06-01":
            os.remove(os.path.join(LOG_DIR, fname))

    # Generate
    cursor = START_DATE
    while cursor <= END_DATE:
        day_start = cursor.replace(hour=0, minute=0, second=0)
        sessions = generate_sessions(day_start)

        for session in sessions:
            safe = session["session_start"].replace(":", "-")
            fname = f"{safe}.json"
            path = os.path.join(LOG_DIR, fname)
            with open(path, "w") as f:
                json.dump(session, f, indent=2, ensure_ascii=False)

        total_day = sum(s["sum_consumption"] for s in sessions)
        print(f"  {cursor.strftime('%Y-%m-%d')} ({cursor.strftime('%a')}): "
              f"{len(sessions)} session(s), ¥{total_day:.4f} total")
        cursor += timedelta(days=1)

    # Also clean daily summaries and reports for the test period
    for subdir in ["daily_summaries", "reports"]:
        d = os.path.expanduser(f"~/.local/share/panelwhale/{subdir}")
        if os.path.isdir(d):
            for fname in os.listdir(d):
                if (fname.endswith(".json") and fname[:10] >= "2026-06-01") or \
                   (fname.startswith("report_2026-06")):
                    os.remove(os.path.join(d, fname))

    print(f"\nDone! Logs saved to {LOG_DIR}")
    print(f"Total files: {len([f for f in os.listdir(LOG_DIR) if f.startswith('2026-06')])}")


if __name__ == "__main__":
    main()
