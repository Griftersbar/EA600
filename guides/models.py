from django.core.paginator import Paginator
from django.db import models
from wagtail import blocks
from wagtail.admin.panels import FieldPanel
from wagtail.fields import StreamField
from wagtail.models import Page

from siteapp.views import homepage_content

from .choosers import PhotoChooserBlock, TourChooserBlock


class GuidePageBase(Page):
    class Meta:
        abstract = True

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context["homepage"] = homepage_content()
        context["page_title"] = self.seo_title or f"{self.title} · EA600"
        context["page_description"] = self.search_description
        return context


class GuideIndexPage(GuidePageBase):
    introduction = models.TextField(blank=True)

    parent_page_types = ["wagtailcore.Page"]
    subpage_types = ["guides.DestinationGuidePage"]
    max_count = 1
    content_panels = Page.content_panels + [FieldPanel("introduction")]

    class Meta:
        verbose_name = "Guides index"

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        guides = (
            DestinationGuidePage.objects.child_of(self)
            .live()
            .public()
            .select_related("cover")
            .order_by("-first_published_at", "title", "pk")
        )
        context["guides"] = Paginator(guides, 12).get_page(request.GET.get("page"))
        return context


class DestinationGuidePage(GuidePageBase):
    introduction = models.TextField(help_text="Short description used on the guides index.")
    cover = models.ForeignKey(
        "siteapp.Photo", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    body = StreamField(
        [
            ("heading", blocks.CharBlock(form_classname="title", template="guides/blocks/heading.html")),
            ("text", blocks.RichTextBlock(features=["bold", "italic", "link", "ol", "ul", "blockquote"])),
            ("photo", PhotoChooserBlock(template="guides/blocks/photo.html")),
            ("featured_tour", TourChooserBlock(template="guides/blocks/tour.html", label="Featured tour")),
        ],
        blank=True,
        use_json_field=True,
    )

    parent_page_types = ["guides.GuideIndexPage"]
    subpage_types = []
    content_panels = Page.content_panels + [
        FieldPanel("introduction"), FieldPanel("cover"), FieldPanel("body"),
    ]

    class Meta:
        verbose_name = "Destination guide"
