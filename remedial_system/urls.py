from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from lessons.admin import admin_site
from lessons import views as lesson_views



urlpatterns = [
    path("admin/", admin_site.urls),
    path("lessons/", include("lessons.urls")),

    # Library app (namespaced) so 'library:' URLs work in templates
    path("library/", include(("library.urls", "library"), namespace="library")),

    # Public website (home + portals)
    path("", include("website.urls")),

    # Optional internal/staff landing using the old lessons home
    path("staff/", lesson_views.home, name="staff_home"),

    # Alias for remedial stats (used by some templates without namespace)
    path("admin/remedial-stats/", lesson_views.remedial_stats, name="remedial_stats"),

    # Deputy normal-classes stats (non-namespaced aliases for existing templates)
    path("admin/normal-stats/", lesson_views.deputy_normal_stats, name="deputy_normal_stats"),
    path(
        "admin/normal-stats/teacher/<int:teacher_id>/",
        lesson_views.remedial_teacher_details,
        name="deputy_normal_teacher_details",
    ),

    # Authentication URLs
    path("accounts/login/", auth_views.LoginView.as_view(template_name="lessons/login.html"), name="login"),
    path("accounts/logout/", lesson_views.simple_logout, name="logout"),

    # Simple password reset info page
    path("accounts/simple-password-reset/", lesson_views.simple_password_reset, name="simple_password_reset"),
]

# Serve media files in DEBUG mode (local dev)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
