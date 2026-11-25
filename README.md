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

## Edit a tour map

In Tour Builder, choose a GPX file under **Route map** and select **Import GPX**. The map follows the points and segments in the file, including its start and finish. GPX files can contain up to 25,000 points and be up to 2 MB.

In a route stop, select **Place on map**, then click or tap its location. You can also enter latitude and longitude in the stop form. Use **Preview** to check the route in the public tour layout, then save or publish it. Tours with an illustrated map can use their existing image and illustrated pins.

Interactive maps use Leaflet and display OpenStreetMap tiles with attribution.

## Create a destination guide

Use the same Django superuser to sign in to Wagtail at `/cms/`. Under **Pages**, open **Guides** and add a **Destination guide**. Add a cover and reorder the heading, text, photo and featured-tour blocks. Photos chosen or uploaded in a guide are available in the EA600 photo library. A featured-tour block links to a published tour in the catalogue.

Save a draft and use Wagtail’s preview before publishing. Published guides appear at `/guides/`. The first setup creates a Norwich example using the existing destination copy and image.

## Railway storage

Mount a persistent volume at `/data` on the preview service. Django uses Railway's `RAILWAY_VOLUME_MOUNT_PATH` for `db.sqlite3` and uploaded photos. The service runs migrations, sets up Guides on the first deployment, and collects static files at startup. Locally, the database and uploads live in the checkout.
