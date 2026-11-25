from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.test import Client, TestCase
from django.urls import reverse
from wagtail.models import GroupApprovalTask, Workflow

from siteapp.models import Tour
from siteapp.test_support import sign_in_verified

from .models import BusinessListing, RoutePlacement


class BusinessListingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = get_user_model().objects.create_superuser(username="listing-reviewer")
        cls.ea600 = Tour.objects.get(slug="ea600")
        cls.norwich = cls.ea600.stops.get(title="Norwich")
        cls.cromer = cls.ea600.stops.get(title="Cromer")
        cls.second_tour = Tour.objects.create(title="Norfolk Loop", slug="norfolk-loop", is_published=True)
        cls.second_norwich = cls.second_tour.stops.create(title="Norwich")

    def listing_data(self, *stops):
        return {
            "name": "Test Tea Room",
            "category": "food",
            "description": "Tea and cakes after a morning exploring Norwich.",
            "address": "Norwich, NR1",
            "link": "https://example.com/tea-room",
            "link_label": "website",
            "stops": [stop.pk for stop in stops],
        }

    def test_wagtail_preview_draft_publication_and_unpublication(self):
        sign_in_verified(self.client, self.editor)
        visitor = Client()
        add_url = reverse("ea600_business_listings:add")
        route_url = self.ea600.get_absolute_url()
        data = self.listing_data(self.norwich)

        add_page = self.client.get(add_url)
        self.assertContains(add_page, f"{self.ea600.title} — Norwich")
        self.assertContains(add_page, 'id="id_photo-chooser"')
        preview = reverse("ea600_business_listings:preview_on_add")
        self.assertTrue(self.client.post(preview, data).json()["is_valid"])
        self.assertContains(self.client.get(preview), data["name"])
        self.assertFalse(BusinessListing.objects.exists())

        self.assertEqual(self.client.post(add_url, {**data, "action-save": "1"}).status_code, 302)
        listing = BusinessListing.objects.get()
        self.assertFalse(listing.live)
        self.assertContains(self.client.get(reverse("ea600_business_listings:list")), listing.name)
        self.assertNotContains(visitor.get(route_url), listing.name)
        edit_url = reverse("ea600_business_listings:edit", args=[listing.pk])
        self.assertEqual(self.client.post(edit_url, {**data, "action-publish": "1"}).status_code, 302)
        listing.refresh_from_db()
        self.assertTrue(listing.live)
        page = visitor.get(route_url)
        self.assertContains(page, listing.name)
        self.assertContains(page, "Near Norwich")
        self.assertContains(page, 'rel="sponsored"')

        revised = {**data, "description": "New seasonal menu", "stops": [self.cromer.pk]}
        self.assertEqual(self.client.post(edit_url, {**revised, "action-save": "1"}).status_code, 302)
        page = visitor.get(route_url)
        self.assertContains(page, "Near Norwich")
        self.assertNotContains(page, "New seasonal menu")
        self.assertNotContains(page, "Near Cromer")
        self.assertEqual(self.client.post(edit_url, {**revised, "action-publish": "1"}).status_code, 302)
        self.assertContains(visitor.get(route_url), "Near Cromer")

        unpublish_url = reverse("ea600_business_listings:unpublish", args=[listing.pk])
        self.assertEqual(self.client.post(unpublish_url).status_code, 302)
        self.assertNotContains(visitor.get(route_url), 'id="places-along-the-route"')

    def test_listings_and_homepage_link_follow_published_route_and_stop(self):
        listing = BusinessListing.objects.create(
            name="North Norfolk Makers", category="shop", description="Locally made gifts.",
            address="Cromer, NR27", link="https://example.com/makers", live=True,
        )
        RoutePlacement.objects.create(listing=listing, stop=self.cromer)
        route_url = self.ea600.get_absolute_url()
        second_url = self.second_tour.get_absolute_url()
        link = f'href="{route_url}#places-along-the-route"'
        self.assertContains(self.client.get(route_url), "Near Cromer")
        self.assertNotContains(self.client.get(second_url), listing.name)
        self.assertContains(self.client.get(reverse("home")), link)
        self.assertNotContains(self.client.get(reverse("home"), {"route": self.second_tour.slug}), link)

        RoutePlacement.objects.create(listing=listing, stop=self.second_norwich)
        other_route = self.client.get(second_url)
        self.assertContains(other_route, listing.name)
        self.assertContains(other_route, "Near Norwich")
        self.assertNotContains(other_route, "Near Cromer")
        self.second_tour.is_published = False
        self.second_tour.save(update_fields=["is_published"])
        self.assertEqual(self.client.get(second_url).status_code, 404)
        self.assertContains(self.client.get(route_url), listing.name)

    def test_editor_must_have_publish_permission(self):
        author = get_user_model().objects.create_user(username="listing-author", is_staff=True)
        author.user_permissions.set(Permission.objects.filter(codename__in=(
            "access_admin", "add_businesslisting", "change_businesslisting",
        )))
        sign_in_verified(self.client, author)
        add_url = reverse("ea600_business_listings:add")
        attempted_publish = self.client.post(add_url, {**self.listing_data(self.norwich), "action-publish": "1"})
        self.assertIn(attempted_publish.status_code, (302, 403))
        self.assertFalse(BusinessListing.objects.filter(live=True).exists())

    def test_moderation_group_can_approve_a_submitted_listing(self):
        reviewers = Group.objects.create(name="Business listing reviewers")
        reviewers.permissions.set(Permission.objects.filter(codename__in=("access_admin", "publish_businesslisting")))
        approver = get_user_model().objects.create_user(username="listing-approver", is_staff=True)
        approver.groups.add(reviewers)
        workflow = Workflow.objects.create(name="Review business listings")
        task = GroupApprovalTask.objects.create(name="Approve listing")
        task.groups.add(reviewers)
        workflow.workflow_tasks.create(task=task, sort_order=0)
        workflow.save()
        workflow.workflow_content_types.create(content_type=ContentType.objects.get_for_model(BusinessListing))

        sign_in_verified(self.client, self.editor)
        response = self.client.post(reverse("ea600_business_listings:add"), {
            **self.listing_data(self.norwich), "action-submit": "1",
        })
        self.assertEqual(response.status_code, 302)
        listing = BusinessListing.objects.get()
        self.assertTrue(listing.workflow_in_progress)
        self.assertFalse(listing.live)

        sign_in_verified(self.client, approver)
        approve_url = reverse("ea600_business_listings:workflow_action", args=[
            listing.pk, "approve", listing.current_workflow_task_state.pk,
        ])
        approval = self.client.post(approve_url)
        self.assertRedirects(approval, reverse("ea600_business_listings:edit", args=[listing.pk]), fetch_redirect_response=False)
        listing.refresh_from_db()
        self.assertTrue(listing.live)
        self.assertContains(Client().get(self.ea600.get_absolute_url()), listing.name)
