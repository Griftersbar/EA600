# EA600 Django app

EA600's homepage and tour catalogue are managed through Django admin. The first migration of the content models imports the existing EA600 route, stops, itinerary, homepage copy and images.

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

Open the homepage at `http://127.0.0.1:8000/` or sign in at `/admin/`.

## Manage content

- Open **Tour Builder** at `/builder/tours/` or from the Wagtail sidebar. Create a tour, choose or upload photos from the shared library, and use the arrows to rearrange stops and itinerary days. **Preview** opens the current form in the public tour layout. Use **Save draft** for a new tour or **Publish changes** to update a live one.
- Add or reuse images under **Photos**, including alt text for meaningful images.
- Add a **Tour** with a title, slug, summary, cover, stops and itinerary days. Choose **Is published** when it is ready for `/tours/`. Pick the homepage's featured route under **Homepage content**.
- Edit homepage text and images under **Homepage content**. Highlights, destinations, planning tips, stories, FAQs and footer photos each have their own admin list.
- Use **Destinations** in Wagtail at `/cms/destinations/` to edit the title, region, text, photo, link and position of each homepage destination card. The editor uses the shared EA600 photo library.

## Create a destination guide

Use the same Django superuser to sign in to Wagtail at `/cms/`. Under **Pages**, open **Guides** and add a **Destination guide**. Add a cover and reorder the heading, text, photo and featured-tour blocks. Photos chosen or uploaded in a guide are available in the EA600 photo library. A featured-tour block links to a published tour in the catalogue.

Save a draft and use Wagtail’s preview before publishing. Published guides appear at `/guides/`. The first setup creates a Norwich example using the existing destination copy and image.

## Railway storage

Mount a persistent volume at `/data` on the preview service. Django uses Railway's `RAILWAY_VOLUME_MOUNT_PATH` for `db.sqlite3` and uploaded photos. The service runs migrations, sets up Guides on the first deployment, and collects static files at startup. Locally, the database and uploads live in the checkout.
