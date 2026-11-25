# EA600 Django app

Manage EA600's site content in Wagtail and its tour catalogue in Tour Builder. The first migration of the content models imports the existing EA600 route, stops, itinerary, homepage copy and images.

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

## Test business applications and billing

Open **Advertise** at `/advertise/`. After signing in with an emailed link, an owner can submit their listing, photo and nearest route stop. It appears as a draft under **Business listings**. Publish it in Wagtail to approve the application. The owner receives an approval email and can choose £12 monthly or £120 annually from **My business listings**. Verified payment makes the approved listing public on the preview. Wagtail-managed listings created by staff can still go live without billing.

Enable email sign-in with `PARTNER_APPLICATIONS_ENABLED=1`. In local development, email prints to the console when `PARTNER_RESEND_API_KEY` and `EMAIL_HOST` are empty. On the preview, set `PARTNER_RESEND_API_KEY` and a verified `DEFAULT_FROM_EMAIL` to send email over HTTPS. If your Railway plan supports outbound SMTP, you can instead configure `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` and `DEFAULT_FROM_EMAIL`.

For a hosted checkout test, use a Stripe sandbox. Set `STRIPE_TEST_SECRET_KEY` and create active GBP recurring prices at £12/month and £120/year. Set their IDs as `STRIPE_TEST_MONTHLY_PRICE` and `STRIPE_TEST_ANNUAL_PRICE`. Enable the test customer portal for payment methods, invoices and cancellation at the end of the billing period. Keep subscription plan changes disabled in the portal.

Register `/advertise/stripe/webhook/` on the preview domain as a test webhook endpoint and set its signing secret as `STRIPE_TEST_WEBHOOK_SECRET`. Subscribe to `checkout.session.completed`, `invoice.paid`, `invoice.payment_failed`, `customer.subscription.updated` and `customer.subscription.deleted`. Keep the key and signing secret in environment variables. This stage accepts test Stripe keys and events. Listings stop appearing when their paid period ends, even if a renewal fails or an expiry event arrives late.

## Run the business listing pilot

Set `PARTNER_PILOT_PREVIEW=1` on a preview service and run `python manage.py seed_partner_pilot` after migrations against that service’s database. The command adds ten fictional businesses on the published EA600 route. Running it again preserves existing demo edits, publication states and counts. Turning the flag off hides the demo cards and activity page.

Open **Places along the route** on `/tours/ea600/` and try a test business’s website, booking or directions link. It returns you to the matching test report at `/advertise/pilot/`. In Wagtail, **Business listings** shows the same 30-day totals. Signed-in owners see totals for listings they own in **My business listings**.

For real listings the links continue to the current website, booking page or directions. The report counts outbound clicks per listing and action over the latest 30 UK calendar days. A click measures interest in a link. It cannot confirm an enquiry, booking or unique visitor. The counters store daily totals.

## Edit a tour map

In Tour Builder, choose a GPX file under **Route map** and select **Import GPX**. The map follows the points and segments in the file, including its start and finish. GPX files can contain up to 25,000 points and be up to 2 MB.

In a route stop, select **Place on map**, then click or tap its location. You can also enter latitude and longitude in the stop form. Use **Preview** to check the route in the public tour layout, then save or publish it. Tours with an illustrated map can use their existing image and illustrated pins.

Interactive maps use Leaflet and display OpenStreetMap tiles with attribution.

## Create a destination guide

Use the same Django superuser to sign in to Wagtail at `/cms/`. Under **Pages**, open **Guides** and add a **Destination guide**. Add a cover and reorder the heading, text, photo and featured-tour blocks. Photos chosen or uploaded in a guide are available in the EA600 photo library. A featured-tour block links to a published tour in the catalogue.

Save a draft and use Wagtail’s preview before publishing. Published guides appear at `/guides/`. The first setup creates a Norwich example using the existing destination copy and image.

## Railway storage

Mount a persistent volume at `/data` on the preview service. Django uses Railway's `RAILWAY_VOLUME_MOUNT_PATH` for `db.sqlite3` and uploaded photos. The service runs migrations, sets up Guides on the first deployment, and collects static files at startup. Locally, the database and uploads live in the checkout.
