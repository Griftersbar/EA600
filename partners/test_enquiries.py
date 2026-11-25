from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from siteapp.test_support import sign_in_verified

from .models import AdvertisingEnquiry, PartnerAccount


@override_settings(PARTNER_APPLICATIONS_ENABLED=False)
class AdvertisingEnquiryTests(TestCase):
    details = {
        "business_name": "Example Deli", "contact_name": "Test Owner",
        "email": "owner+ea600@example.test", "location": "Norwich",
        "message": "Which stops are available near Norwich?",
    }

    def setUp(self):
        cache.clear()
        self.advertise = reverse("partners:advertise")
        self.enquire = reverse("partners:enquire")
        self.post_data = {f"enquiry-{name}": value for name, value in self.details.items()}

    def test_business_can_enquire_while_applications_are_closed(self):
        page = self.client.get(self.advertise)
        self.assertContains(page, "Make an enquiry")
        self.assertContains(page, "Online listing applications are currently closed.")
        self.assertRedirects(self.client.get(self.enquire), self.advertise + "#advertising-enquiry")
        result = self.client.post(self.enquire, self.post_data)
        self.assertRedirects(result, self.advertise + "#advertising-enquiry", fetch_redirect_response=False)
        self.assertContains(self.client.get(self.advertise), "We’ve received your enquiry")
        self.assertNotContains(self.client.get(self.advertise), "We’ve received your enquiry")
        enquiry = AdvertisingEnquiry.objects.get()
        self.assertEqual(enquiry.email, self.details["email"])
        self.assertEqual(enquiry.message, self.details["message"])
        self.assertEqual(enquiry.status, AdvertisingEnquiry.Status.NEW)
        self.assertFalse(PartnerAccount.objects.exists())

    def test_protects_posts_and_limits_repeated_submissions(self):
        csrf_client = Client(enforce_csrf_checks=True)
        self.assertEqual(csrf_client.post(self.enquire, self.post_data).status_code, 403)
        invalid = self.client.post(self.enquire, {**self.post_data, "enquiry-email": "wrong"})
        self.assertContains(invalid, "Enter a valid email address", status_code=400)
        self.assertContains(invalid, self.details["business_name"], status_code=400)
        self.assertFalse(AdvertisingEnquiry.objects.exists())
        for _ in range(5):
            self.assertEqual(self.client.post(self.enquire, self.post_data).status_code, 302)
        blocked = self.client.post(self.enquire, self.post_data)
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(blocked["Retry-After"], "900")
        self.assertEqual(AdvertisingEnquiry.objects.count(), 5)

    def test_wagtail_inbox_is_private_and_supports_reply_status(self):
        enquiry = AdvertisingEnquiry.objects.create(**self.details)
        index = reverse("ea600_advertising_enquiries:index")
        edit = reverse("ea600_advertising_enquiries:edit", args=[enquiry.pk])
        self.assertEqual(self.client.get(index).status_code, 302)
        staff = get_user_model().objects.create_user(username="general-editor", is_staff=True)
        staff.user_permissions.add(Permission.objects.get(codename="access_admin"))
        sign_in_verified(self.client, staff)
        self.assertNotContains(self.client.get(index, follow=True), enquiry.business_name)

        staff.user_permissions.add(Permission.objects.get(codename="change_advertisingenquiry"))
        inbox = self.client.get(index)
        self.assertContains(inbox, enquiry.business_name)
        self.assertNotContains(inbox, f'href="{index}new/"')
        self.assertEqual(self.client.get(index + "new/").status_code, 404)
        detail = self.client.get(edit)
        self.assertContains(detail, "mailto:owner%2Bea600@example.test")
        self.assertContains(detail, enquiry.message)
        self.assertEqual(self.client.post(edit, {"status": "replied", "business_name": "Changed"}).status_code, 302)
        enquiry.refresh_from_db()
        self.assertEqual(enquiry.status, AdvertisingEnquiry.Status.REPLIED)
        self.assertEqual(enquiry.business_name, self.details["business_name"])
