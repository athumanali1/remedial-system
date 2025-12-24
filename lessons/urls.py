from django.conf import settings
from django.conf.urls.static import static
from django.urls import path
from . import views

urlpatterns = [
    # Teacher views
    path("lesson/add/", views.add_lesson_teacher, name="add_lesson"),
    path("teacher/dashboard/", views.teacher_dashboard, name="teacher_dashboard"),
    path("teacher/normal-stats/", views.teacher_normal_stats, name="teacher_normal_stats"),
    path("teacher/update-profile-picture/", views.update_profile_picture, name="update_profile_picture"),
    path("teacher/normal-timetable/", views.teacher_normal_timetable, name="teacher_normal_timetable"),
    path("teacher/remedial-timetable/", views.teacher_remedial_timetable, name="teacher_remedial_timetable"),
    path("mark_attended/<int:lesson_id>/", views.mark_attended, name="mark_attended"),
    path("student/payments/", views.student_payments, name="student_payments"),

    # Normal timetable tools (deputy / admin)
    path("timetable/builder/", views.timetable_builder, name="timetable_builder"),
    path("timetable/master/", views.timetable_master, name="timetable_master"),
    path("timetable/generate-week/", views.generate_week_lessons, name="generate_week_lessons"),

    # Remedial timetable tools (admin/superuser)
    path("remedial/timetable/builder/", views.remedial_timetable_builder, name="remedial_timetable_builder"),
    path("remedial/timetable/master/", views.remedial_timetable_master, name="remedial_timetable_master"),
    path("remedial/timetable/generate-week/", views.generate_remedial_week_lessons, name="generate_remedial_week_lessons"),

    # AJAX endpoints
    path("ajax/load-timetables/", views.load_timetables, name="ajax_load_timetables"),
    path("ajax/teacher_subjects/", views.ajax_teacher_subjects, name="ajax_teacher_subjects"),
    path("filter_timetables/", views.get_timetables, name="filter_timetables"),
     path('student-payments/', views.student_payments, name='student_payments'),
    path('add-student-ajax/', views.add_student_ajax, name='add_student_ajax'),
    path('edit-student-ajax/<int:student_id>/', views.edit_student_ajax, name='edit_student_ajax'),
    path('delete-student-ajax/<int:student_id>/', views.delete_student_ajax, name='delete_student_ajax'),
    path('admin-payments/', views.admin_payments, name='admin_payments'),
    
    # External trigger for notifications
    path('trigger-notifications/', views.trigger_notifications, name='trigger_notifications'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
