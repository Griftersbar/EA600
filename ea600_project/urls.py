from django.contrib import admin
from django.urls import path, re_path

from siteapp import views

urlpatterns = [
    path("", views.home, name="home"),
    path("tours/", views.tour_list, name="tour_list"),
    path("tours/<slug:slug>/", views.tour_detail, name="tour_detail"),
    path("stories/<slug:slug>/", views.story_detail, name="story_detail"),
    path("admin/", admin.site.urls),
    re_path(r"^(?P<name>(?:assets|css|js)/.+)$", views.legacy_static),
    re_path(r"^media/(?P<name>photos/[a-f0-9]{32}\.(?:jpe?g|png|webp|gif))$", views.photo_file, name="photo_file"),
]
