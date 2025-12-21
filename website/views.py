from django.shortcuts import render, redirect
from django.urls import reverse

from .models import Page, GalleryImage, Tender, ContactInfo, UpcomingEvent


def _get_page(slug: str):
    try:
        return Page.objects.get(slug=slug, is_published=True)
    except Page.DoesNotExist:
        return None


def home(request):
    page = _get_page("home")
    events = UpcomingEvent.objects.filter(is_published=True).order_by("date")[:5]
    return render(request, "website/home.html", {"page": page, "events": events})


def about(request):
    page = _get_page("about")
    return render(request, "website/page.html", {"page": page})


def management(request):
    page = _get_page("management")
    return render(request, "website/page.html", {"page": page})


def school(request):
    page = _get_page("school")
    return render(request, "website/page.html", {"page": page})


def chapel(request):
    page = _get_page("chapel")
    return render(request, "website/page.html", {"page": page})


def gallery(request):
    images = GalleryImage.objects.filter(is_published=True)
    return render(request, "website/gallery.html", {"images": images})


def tenders(request):
    tenders_qs = Tender.objects.filter(is_published=True)
    return render(request, "website/tenders.html", {"tenders": tenders_qs})


def contact(request):
    info = ContactInfo.objects.first()
    return render(request, "website/contact.html", {"info": info})


def more(request):
    page = _get_page("more")
    return render(request, "website/page.html", {"page": page})


def staff_portal(request):
    """Entry point from the public website into the staff system.

    Redirects to the existing login page; from there your role-based logic
    (teacher / deputy / remedial admin) decides which dashboard to show.
    """

    return redirect(reverse("login"))
