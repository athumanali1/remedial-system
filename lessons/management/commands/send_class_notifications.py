from datetime import timedelta
import json

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from pywebpush import webpush, WebPushException

from lessons.models import (
    NormalLessonSlot,
    TeacherPushSubscription,
    SentClassNotification,
    SentRemedialNotification,
    Timetable,
    Week,
    LessonRecord,
)


class Command(BaseCommand):
    help = "Send web push notifications for classes starting in the next hour (hourly scheduling)."

    def handle(self, *args, **options):
        now = timezone.localtime()
        
        # Only run during school hours (8:00 - 16:00)
        if now.hour < 8 or now.hour >= 16:
            self.stdout.write("Outside school hours (8:00-16:00); skipping.")
            return
        
        # Check for classes starting in the next hour
        # We'll send notifications at 5 minutes before start time only
        notification_times = [5]  # minutes before class
        
        for minutes_before in notification_times:
            # Calculate the target time when we should send notifications
            notification_target = now + timedelta(minutes=minutes_before)
            target_time = notification_target.time().replace(second=0, microsecond=0)
            
            weekday_codes = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            day_code = weekday_codes[notification_target.weekday()]

            # ---------- Normal classes (NormalLessonSlot) ----------
            slots = (
                NormalLessonSlot.objects
                .filter(day=day_code, start_time=target_time)
                .select_related("teacher", "class_group", "subject_fk")
            )

            vapid_public = getattr(settings, "WEBPUSH_VAPID_PUBLIC_KEY", "")
            vapid_private = getattr(settings, "WEBPUSH_VAPID_PRIVATE_KEY", "")
            vapid_claims = getattr(settings, "WEBPUSH_VAPID_CLAIMS", {})

            if not vapid_public or not vapid_private:
                self.stderr.write("VAPID keys are not configured; skipping push sending.")
                return

            today = notification_target.date()

            # Normal lessons
            if slots.exists():
                self.stdout.write(f"Processing {slots.count()} normal slots starting in {minutes_before} minutes:")

                for slot in slots:
                    teacher = slot.teacher

                    # Avoid duplicate notifications for the same slot/date/time
                    sent, created = SentClassNotification.objects.get_or_create(
                        slot=slot,
                        date=today,
                        start_time=slot.start_time,
                    )
                    if not created:
                        # Already sent for this class today
                        continue

                    subs = TeacherPushSubscription.objects.filter(teacher=teacher)
                    if not subs.exists():
                        self.stdout.write(f"- {teacher} has no push subscriptions (normal); skipping.")
                        continue

                    class_name = slot.class_group.name
                    subject_name = slot.subject_fk.name
                    tstr = slot.start_time.strftime("%H:%M")

                    payload = json.dumps({
                        "title": f"Next class in {minutes_before} minutes",
                        "body": f"{subject_name} with {class_name} at {tstr}",
                        "url": "/lessons/teacher/dashboard/",
                    })

                    for sub in subs:
                        try:
                            webpush(
                                subscription_info={
                                    "endpoint": sub.endpoint,
                                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                                },
                                data=payload,
                                vapid_private_key=vapid_private,
                                vapid_claims=vapid_claims,
                            )
                            self.stdout.write(
                                f"Sent normal notification to {teacher} ({sub.endpoint[:40]}...) "
                                f"for {subject_name} with {class_name} at {tstr}."
                            )
                        except WebPushException as exc:
                            self.stderr.write(f"WebPush error for {teacher} (normal): {exc}")

            # ---------- Remedial classes (Timetable) ----------
            remedial_tts = (
                Timetable.objects
                .filter(day=day_code, start_time=target_time)
                .select_related("teacher", "subject_fk")
                .prefetch_related("class_groups")
            )

            if remedial_tts.exists():
                self.stdout.write(f"Processing {remedial_tts.count()} remedial slots starting in {minutes_before} minutes:")

                for tt in remedial_tts:
                    teacher = tt.teacher

                    sent_r, created_r = SentRemedialNotification.objects.get_or_create(
                        timetable=tt,
                        date=today,
                        start_time=tt.start_time,
                    )
                    if not created_r:
                        # Already notified for this remedial class today
                        continue

                    subs = TeacherPushSubscription.objects.filter(teacher=teacher)
                    if not subs.exists():
                        self.stdout.write(f"- {teacher} has no push subscriptions (remedial); skipping.")
                        continue

                    class_names = ", ".join(sorted(c.name for c in tt.class_groups.all())) or "(No class)"
                    subject_name = tt.subject_fk.name if tt.subject_fk else "Remedial lesson"
                    tstr = tt.start_time.strftime("%H:%M")

                    payload_r = json.dumps({
                        "title": f"Next remedial class in {minutes_before} minutes",
                        "body": f"{subject_name} with {class_names} at {tstr}",
                        "url": "/lessons/teacher/dashboard/",
                    })

                    for sub in subs:
                        try:
                            webpush(
                                subscription_info={
                                    "endpoint": sub.endpoint,
                                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                                },
                                data=payload_r,
                                vapid_private_key=vapid_private,
                                vapid_claims=vapid_claims,
                            )
                            self.stdout.write(
                                f"Sent remedial notification to {teacher} ({sub.endpoint[:40]}...) "
                                f"for {subject_name} with {class_names} at {tstr}."
                            )
                        except WebPushException as exc:
                            self.stderr.write(f"WebPush error for {teacher} (remedial): {exc}")

        self.stdout.write("Done.")
