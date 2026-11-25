from django.contrib import admin
from django.urls import include, path, re_path
from wagtail import urls as wagtail_urls
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.documents import urls as wagtaildocs_urls

from siteapp import builder_views, editor_auth, release_history, views

urlpatterns = [
    path("", views.home, name="home"),
    path("tours/", views.tour_list, name="tour_list"),
    path("tours/<slug:slug>/", views.tour_detail, name="tour_detail"),
    path("advertise/", include("partners.urls")),
    path("builder/tours/", builder_views.builder_index, name="builder_index"),
    path("builder/tours/new/", builder_views.builder_edit, name="builder_new"),
    path("builder/tours/<int:pk>/", builder_views.builder_edit, name="builder_edit"),
    path(
        "builder/tours/<int:pk>/unpublish/", builder_views.builder_lifecycle,
        {"action": "unpublish"}, name="builder_unpublish",
    ),
    path(
        "builder/tours/<int:pk>/delete/", builder_views.builder_lifecycle,
        {"action": "delete"}, name="builder_delete",
    ),
    path("builder/photos/", builder_views.builder_photos, name="builder_photos"),
    path("builder/route-track/", builder_views.builder_import_gpx, name="builder_import_gpx"),
    path("stories/<slug:slug>/", views.story_detail, name="story_detail"),
    path("admin/login/", editor_auth.editor_login, {"entry": "django"}, name="editor_admin_login"),
    path("cms/login/", editor_auth.editor_login, {"entry": "wagtail"}, name="editor_wagtail_login"),
    path("editor/verify/", editor_auth.editor_verify, name="editor_verify"),
    path("editor/recovery-codes/", editor_auth.editor_recovery_codes, name="editor_recovery_codes"),
    path("admin/release-notes/", admin.site.admin_view(release_history.release_notes), name="admin_release_notes"),
    path("admin/", admin.site.urls),
    path("cms/", include(wagtailadmin_urls)),
    path("documents/", include(wagtaildocs_urls)),
    path("guides/", include(wagtail_urls)),
    re_path(r"^(?P<name>(?:assets|css|js)/.+)$", views.legacy_static),
    re_path(r"^media/(?P<name>photos/[a-f0-9]{32}\.(?:jpe?g|png|webp|gif))$", views.photo_file, name="photo_file"),
    re_path(r"^media/(?P<name>(?:original_images|images|avatar_images)/[\w.-]+\.(?i:avif|jpe?g|png|webp|gif))$", views.photo_file),
]
