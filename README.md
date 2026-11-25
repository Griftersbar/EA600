# EA600 Django app

Manage EA600's site content in Wagtail and its tour catalogue in Tour Builder. The first migration of the content models imports the existing EA600 route, stops, itinerary, homepage copy and images.

The 3-day and 14-day EA600 itineraries are added as published tours. Select either from the homepage route picker, or edit its stops, approximate map pins and daily descriptions in Tour Builder.

## Run locally

Use Python 3.11 or newer for Wagtail 8.1.

```sh
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py bootstrap_guides
python manage.py createsuperuser
python manage.py runserver
```

Open the homepage at `http://127.0.0.1:8000/` or sign in to Wagtail at `/cms/`.

## Editor sign-in

Django admin, Wagtail, and Tour Builder share an editor session. On your first sign-in, scan the QR code in an authenticator app and enter the six-digit code. Save the recovery codes in a password manager when they appear. Each recovery code works once.

Django admin and Wagtail share a 15-minute password cooldown after five failures for the account or client address. Failed authenticator and recovery codes are also throttled. On the Railway public domain the rate limiter uses the client address set by the Railway HTTP edge.

If you lose access to your authenticator, choose **Use a recovery code** after entering your password. A site superuser can reset MFA for an editor by removing that user's TOTP and static devices in Django admin after verifying their identity. At the next sign-in the editor can enrol a new authenticator and save a new set of codes.

## Release notes

Django superusers can open **Release notes** from the admin header or at `/admin/release-notes/`. The screen shows the running version, the build revision on Railway, and the history of app changes.

Prepend a dated entry to `siteapp/release_notes.json` in the same change as each app release. Use the next patch number for fixes and refinements or the next minor number for new functionality. Keep earlier entries so the history ships with each release.

## Manage content

- Use **Homepage** in Wagtail at `/cms/homepage/` to edit copy and images or feature a published tour.
- Open **Settings → Site settings** at `/cms/site-settings/` to edit the site name, logos, footer text, contact details and social links.
- Open **Content** in the Wagtail sidebar to manage destination cards, planning tips, stories, FAQs, highlights and footer photos. Select **Published** on a story to make it public. Image fields use the shared EA600 photo library.
- Open **EA600 Photos** at `/cms/photos/` to browse the shared library, upload photos, or edit titles and alt text. Wagtail photo fields show a thumbnail of the selected photo. The same library is available in Tour Builder.
- Open **Tour Builder** at `/builder/tours/` or from the Wagtail sidebar. Create a tour, choose or upload photos, and use the arrows to rearrange stops and itinerary days. **Preview** opens the current form in the public tour layout. Use **Save draft** for a new tour or **Publish changes** to update a live one.
- Under **Manage tour**, use **Unpublish tour** to take a published tour offline and keep it as a draft. **Delete tour** opens a confirmation page for permanent deletion. Photos stay in the shared library.

## Publish a business listing

In Wagtail, open **Business listings** and select **Add business listing**. Enter the business name, category, address, description and website or booking link. Choose an existing photo or upload one from the photo chooser. Under **Route stops**, choose the nearest stop on each relevant route.

Save a draft and use **Preview** to review the card and its placements. Select **Publish** when it’s ready. Published cards appear under **Places along the route**, grouped by stop. Use **Unpublish** to take a listing offline and keep its draft. A route must be published for its placements to appear.

Wagtail group permissions control who can add, change and publish business listings. To require sign-off for editors, assign a moderation workflow to **Business listing** under **Settings → Workflows** and reserve direct publish permission for reviewers.

## Review advertising enquiries

Visitors can submit a question on **Advertise** at `/advertise/#advertising-enquiry`. Submissions go to **Advertising enquiries** in Wagtail. Open an enquiry, use the email address to reply in your mail app, then mark it **Replied**. Wagtail group permissions control who can see or manage enquiries. The form works whenever the site is available, including while online listing applications are closed.

Select **Create business listing** on an enquiry to start a draft with its business name and location filled in. Complete the public details and choose a published route stop. The draft is linked to the enquiry's reply email and follows the usual approval and payment process. Converted enquiries link to their listing and are marked **Converted** in the inbox. Staff need permission to change enquiries and add business listings to convert an enquiry.

Open **Settings → Advertise page** in Wagtail to change the page copy and buttons. Under **Page content → Listing package**, edit the monthly and annual prices in pounds or control whether visitors see the prices. Saved prices appear on the public page and apply to new checkouts. Renewals use the price already attached to each subscription. On the **Enquiry form** tab, edit field labels and help text, change required fields, and add, remove or reorder questions. Keep one reply email field so staff can respond. New answers appear in **Advertising enquiries**, with custom questions saved under the labels used at submission.

On **Page content**, choose the hero photo and edit the information cards and callouts under **Advertiser information**. The information explains which businesses can advertise, what a listing includes, and what happens after an enquiry.

## Business applications and billing

Open **Advertise** at `/advertise/`. After signing in with an emailed link, an owner can submit their listing, photo and nearest route stop. It appears as a draft under **Business listings**. Publish it in Wagtail to approve the application. The owner receives an approval email and can select **Choose a payment plan** from **My business listings**. The payment page shows the current monthly and annual prices and opens Stripe Checkout. A verified paid invoice makes the approved listing public. Wagtail-managed listings created by staff can still go live without billing.

Enable email sign-in with `PARTNER_APPLICATIONS_ENABLED=1`. In local development, email prints to the console when `PARTNER_RESEND_API_KEY` and `EMAIL_HOST` are empty. On the preview, set `PARTNER_RESEND_API_KEY` and a verified `DEFAULT_FROM_EMAIL` to send email over HTTPS. If your Railway plan supports outbound SMTP, you can instead configure `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` and `DEFAULT_FROM_EMAIL`.

### Stripe test checkout

The default `PARTNER_BILLING_MODE=test` uses a Stripe sandbox. Set `STRIPE_TEST_SECRET_KEY` and create one active monthly and one active annual Stripe price in GBP. Set their IDs as `STRIPE_TEST_MONTHLY_PRICE` and `STRIPE_TEST_ANNUAL_PRICE`. Checkout uses these products and intervals with the current prices from Wagtail.

Select **Advertiser payments** in the header of a saved business listing in Wagtail to see its payment status. With `PARTNER_PILOT_PREVIEW=1` in test mode, a superuser signed in with two-factor authentication can select **Open My business listings** for an approved listing. The sandbox session lasts up to 20 minutes and opens without a sign-in email. Select **Choose a payment plan** to review prices and test checkout when Stripe credentials are configured.

### Live Stripe checkout

Set `PARTNER_BILLING_MODE=live` on the service that should accept real payments. Use an activated Stripe account and set `STRIPE_LIVE_SECRET_KEY`, `STRIPE_LIVE_MONTHLY_PRICE`, and `STRIPE_LIVE_ANNUAL_PRICE` using its live key and active GBP recurring prices. Prior test payments cannot unlock listings in live mode. A new live checkout for a test application keeps the listing and owner and starts a fresh Stripe checkout.

### Webhook and subscription management

Register the service's `/advertise/stripe/webhook/` URL in the matching Stripe mode, with `STRIPE_TEST_WEBHOOK_SECRET` for test or `STRIPE_LIVE_WEBHOOK_SECRET` for live. Subscribe to `checkout.session.completed`, `invoice.paid`, `invoice.payment_failed`, `customer.subscription.updated` and `customer.subscription.deleted`. Store the API key and webhook signing secret as Railway variables. Enable Stripe's customer portal for payment methods, invoices and cancellation at the end of the billing period. Keep subscription plan changes disabled in the portal. Listings stop appearing when their paid period ends, even if a renewal fails or an expiry event arrives late.

## Run the business listing pilot

Set `PARTNER_PILOT_PREVIEW=1` on a preview service and run `python manage.py seed_partner_pilot` after migrations against that service’s database. The command adds ten fictional businesses on the published EA600 route. Running it again preserves existing demo edits, publication states and counts. Turning the flag off hides the demo cards and activity page.

Open **Places along the route** on `/tours/ea600/` and try a test business’s website, booking or directions link. It returns you to the matching test report at `/advertise/pilot/`. In Wagtail, **Business listings** shows the same 30-day totals. Signed-in owners see totals for listings they own in **My business listings**.

For real listings the links continue to the current website, booking page or directions. The report counts outbound clicks per listing and action over the latest 30 UK calendar days. A click measures interest in a link. It cannot confirm an enquiry, booking or unique visitor. The counters store daily totals.

## Edit a tour map

In Tour Builder, choose a GPX file under **Route map** and select **Import GPX**. The map follows the points and segments in the file, including its start and finish. GPX files can contain up to 25,000 points and be up to 2 MB.

In a route stop, select **Place on map**, then click or tap its location. You can also enter latitude and longitude in the stop form. Use **Preview** to check the route in the public tour layout, then save or publish it. Tours with an illustrated map can use their existing image and illustrated pins.

Interactive maps use Leaflet and display OpenStreetMap tiles with attribution.

## Edit a destination page

Open **Content → Destinations** in Wagtail to edit the description, cover photo, gallery and visitor information link. Saved destinations have a public page at `/destinations/<slug>/` and a card on the homepage.

To link a route to a destination, open the stop in Tour Builder and select its **Destination**, then publish the route. Existing matching stops on the three EA600 routes are linked when the destination pages are first installed. Approved business listings at linked stops appear on the destination page with the same publication and payment rules as on the route.

## Create a destination guide

Use the same Django superuser to sign in to Wagtail at `/cms/`. Under **Pages**, open **Guides** and add a **Destination guide**. Add a cover and reorder the heading, text, photo and featured-tour blocks. Photos chosen or uploaded in a guide are available in the EA600 photo library. A featured-tour block links to a published tour in the catalogue.

Save a draft and use Wagtail’s preview before publishing. Published guides appear at `/guides/`. The first setup creates a Norwich example using the existing destination copy and image.

## Railway storage

Mount a persistent volume at `/data` on the preview service. Django uses Railway's `RAILWAY_VOLUME_MOUNT_PATH` for `db.sqlite3` and uploaded photos. The service runs migrations, sets up Guides on the first deployment, and collects static files at startup. Locally, the database and uploads live in the checkout.
