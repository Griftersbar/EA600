# EA600 Django app

EA600's homepage and tour catalogue are managed through Django admin. The first migration of the content models imports the existing EA600 route, stops, itinerary, homepage copy and images.

## Run locally

```sh
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open the homepage at `http://127.0.0.1:8000/` or sign in at `/admin/`.

## Manage content

- Add or reuse images under **Photos**, including alt text for meaningful images.
- Add a **Tour** with a title, slug, summary, cover, stops and itinerary days. Choose **Is published** when it is ready for `/tours/`. Pick the homepage's featured route under **Homepage content**.
- Edit homepage text and images under **Homepage content**. Highlights, destinations, planning tips, stories, FAQs and footer photos each have their own admin list.

## Railway storage

Mount a persistent volume at `/data` on the preview service. Django uses Railway's `RAILWAY_VOLUME_MOUNT_PATH` for `db.sqlite3` and uploaded photos. The service runs migrations and collects static files at startup. Locally, the database and uploads live in the checkout.
