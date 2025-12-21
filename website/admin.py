from django.contrib import admin

from .models import Page, GalleryImage, Tender, ContactInfo, UpcomingEvent


@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    list_display = ("slug", "title", "is_published", "updated_at")
    list_filter = ("is_published",)
    search_fields = ("slug", "title", "body")
    prepopulated_fields = {"slug": ("title",)}


@admin.register(GalleryImage)
class GalleryImageAdmin(admin.ModelAdmin):
    list_display = ("title", "is_published", "created_at")
    list_filter = ("is_published",)
    search_fields = ("title", "caption")


@admin.register(Tender)
class TenderAdmin(admin.ModelAdmin):
    list_display = ("title", "publish_date", "closing_date", "is_published")
    list_filter = ("is_published", "publish_date")
    search_fields = ("title", "description")


@admin.register(ContactInfo)
class ContactInfoAdmin(admin.ModelAdmin):
    list_display = ("school_name", "phone", "email")


@admin.register(UpcomingEvent)
class UpcomingEventAdmin(admin.ModelAdmin):
    list_display = ("title", "date", "is_published")
    list_filter = ("is_published", "date")
    search_fields = ("title", "description")
