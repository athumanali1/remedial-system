from django.db import models
from ckeditor_uploader.fields import RichTextUploadingField


class Page(models.Model):
    """Simple editable page, e.g. Home, About, Management, School, Chapel, More."""

    slug = models.SlugField(max_length=50, unique=True)
    title = models.CharField(max_length=200)
    body = RichTextUploadingField(blank=True)
    hero_image = models.ImageField(upload_to="pages/", blank=True, null=True)
    is_published = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["slug"]

    def __str__(self) -> str:
        return self.title


class GalleryImage(models.Model):
    """Photo gallery item for the school website."""

    title = models.CharField(max_length=200)
    image = models.ImageField(upload_to="gallery/")
    caption = models.CharField(max_length=255, blank=True)
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title


class Tender(models.Model):
    """Tenders/announcements for the AHS Tenders page."""

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    document = models.FileField(upload_to="tenders/", blank=True, null=True)
    publish_date = models.DateField()
    closing_date = models.DateField(blank=True, null=True)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ["-publish_date"]

    def __str__(self) -> str:
        return self.title


class ContactInfo(models.Model):
    """Single record holding contact details for the Contact page."""

    school_name = models.CharField(max_length=255, blank=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=100, blank=True)
    email = models.EmailField(blank=True)
    map_embed = models.TextField(blank=True, help_text="Optional HTML embed for map (iframe, etc.)")

    class Meta:
        verbose_name = "Contact information"
        verbose_name_plural = "Contact information"

    def __str__(self) -> str:
        return self.school_name or "Contact information"


class UpcomingEvent(models.Model):
    """Simple upcoming event item for the home page."""

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    date = models.DateField(blank=True, null=True)
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self) -> str:
        return self.title
