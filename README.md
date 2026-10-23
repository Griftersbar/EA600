# EA600 Django app

This project keeps the existing static landing page and serves it through Django so you can build on it as a normal Django app.

Run it with:

    python -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    python manage.py runserver

Then open:

    http://127.0.0.1:8000/

The homepage is currently served from the existing `index.html` file, and the original `css/`, `js/`, and `assets/` folders remain available for styling and asset work.
