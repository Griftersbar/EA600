from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from wagtail.test.utils.form_data import nested_form_data, streamfield

from siteapp.test_support import sign_in_verified

from .models import AdvertisePageSettings, AdvertisingEnquiry, PartnerAccount


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
        self.assertContains(page, "Who can advertise?")
        self.assertContains(page, "Click reporting")
        self.assertNotContains(page, "None</div>")
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

    def edit_advertise_settings(self, fields, *, sections=(), **copy):
        settings_url = reverse("wagtailsettings:edit", args=["partners", "advertisepagesettings", AdvertisePageSettings.load().pk])
        field_form = self.client.get(settings_url).context["form"]
        values = {
            name: field_form[name].value()
            for name in field_form.fields if name not in ("enquiry_fields", "advertiser_sections")
        }
        values["hero_photo"] = values["hero_photo"] or ""
        data = {**values, **copy, "enquiry_fields": streamfield(fields), "advertiser_sections": streamfield(sections)}
        return self.client.post(settings_url, nested_form_data(data))

    def test_wagtail_settings_control_page_form_and_saved_answers(self):
        editor = get_user_model().objects.create_superuser(username="advertise-editor")
        sign_in_verified(self.client, editor)
        fields = [
            ("reply_email", {"label": "Your reply address"}),
            ("standard", {"field": "contact_name", "label": "Contact person"}),
            ("dropdown", {
                "label": "Listing interest", "required": True, "help_text": "<b>Choose a type</b>",
                "options": {
                    "count": "2",
                    "0": {"value": "Food and drink", "order": "0", "deleted": ""},
                    "1": {"value": "Accommodation", "order": "1", "deleted": ""},
                },
            }),
        ]
        saved = self.edit_advertise_settings(
            fields, title="Advertise your business", enquiry_submit_label="Ask about a listing",
            enquiry_confirmation="Thank you. We’ll be in touch.", show_plan_prices=False,
            monthly_price="14.50", annual_price="145.25",
            hero_subtitle="Welcome local businesses",
            sections=[("note", {"heading": "Questions before applying?", "description": "Tell us where you are based."})],
        )
        self.assertEqual(saved.status_code, 302)
        editor_page = self.client.get(saved["Location"])
        self.assertContains(editor_page, "Monthly price (£)")
        self.assertContains(editor_page, "Annual price (£)")
        self.assertIn('value="14.50"', str(editor_page.context["form"]["monthly_price"]))
        self.assertIn('value="145.25"', str(editor_page.context["form"]["annual_price"]))
        visitor = Client()
        page = visitor.get(self.advertise)
        self.assertContains(page, "Advertise your business")
        self.assertContains(page, "Welcome local businesses")
        self.assertContains(page, "Questions before applying?")
        self.assertContains(page, "Ask about a listing")
        self.assertContains(page, "&lt;b&gt;Choose a type&lt;/b&gt;")
        self.assertNotContains(page, "£14.50 a month")
        form = page.context["enquiry_form"]
        extra_name = form.extra_fields[0]
        self.assertEqual(list(form.fields), ["email", "contact_name", extra_name])
        self.assertFalse(form.fields["contact_name"].required)
        self.assertTrue(form.fields["email"].required)

        reply = {"enquiry-email": "new-business@example.test"}
        self.assertEqual(visitor.post(self.enquire, reply).status_code, 400)
        self.assertEqual(visitor.post(self.enquire, {**reply, f"enquiry-{extra_name}": "Invalid"}).status_code, 400)
        response = visitor.post(self.enquire, {**reply, f"enquiry-{extra_name}": "Food and drink"})
        self.assertEqual(response.status_code, 302)
        self.assertContains(visitor.get(self.advertise), "Thank you. We’ll be in touch.")
        enquiry = AdvertisingEnquiry.objects.get()
        self.assertEqual(enquiry.contact_name, "")
        self.assertEqual(enquiry.additional_answers, [{"label": "Listing interest", "value": "Food and drink"}])

        edit_url = reverse("ea600_advertising_enquiries:edit", args=[enquiry.pk])
        detail = self.client.get(edit_url)
        self.assertContains(detail, "Listing interest")
        self.assertContains(detail, "Food and drink")
        self.assertContains(self.client.get(reverse("ea600_advertising_enquiries:index")), enquiry.email)
        self.assertEqual(self.edit_advertise_settings([fields[0]], show_plan_prices=True).status_code, 302)
        self.assertContains(self.client.get(edit_url), "Listing interest")
        public = visitor.get(self.advertise)
        self.assertContains(public, "£14.50 a month")
        self.assertContains(public, "£145.25 a year")

        invalid = self.edit_advertise_settings([fields[0]], monthly_price="0.01", annual_price="12.125")
        self.assertEqual(invalid.status_code, 200)
        self.assertIn("monthly_price", invalid.context["form"].errors)
        self.assertIn("annual_price", invalid.context["form"].errors)
        self.assertContains(visitor.get(self.advertise), "£14.50 a month")

    def test_wagtail_requires_exactly_one_reply_address_and_unique_standard_fields(self):
        editor = get_user_model().objects.create_superuser(username="enquiry-settings-editor")
        sign_in_verified(self.client, editor)
        standard = ("standard", {"field": "location", "label": "Location"})
        reply = ("reply_email", {"label": "Reply email"})
        for fields in ([standard], [reply, reply]):
            with self.subTest(fields=fields):
                response = self.edit_advertise_settings(fields, title="Invalid version")
                self.assertEqual(response.status_code, 200)
                self.assertIn("enquiry_fields", response.context["form"].errors)
                self.assertEqual(AdvertisePageSettings.load().title, "Advertise on EA600")
        self.assertContains(self.edit_advertise_settings([reply, standard, standard]), "Use each standard enquiry field once")
