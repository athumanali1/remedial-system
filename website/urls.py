from django.urls import path

from . import views

app_name = "website"

urlpatterns = [
    path("", views.home, name="home"),
    path("about/", views.about, name="about"),
    path("management/", views.management, name="management"),
    path("school/", views.school, name="school"),
    path("chapel/", views.chapel, name="chapel"),
    path("gallery/", views.gallery, name="gallery"),
    path("tenders/", views.tenders, name="tenders"),
    path("contact/", views.contact, name="contact"),
    path("more/", views.more, name="more"),
    path("staff/", views.staff_portal, name="staff_portal"),
]
