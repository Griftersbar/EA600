from django.urls import path

from . import views


app_name = "partners"
urlpatterns = [
    path("", views.advertise, name="advertise"),
    path("enquire/", views.enquire, name="enquire"),
    path("go/<int:pk>/<slug:action>/", views.listing_click, name="listing_click"),
    path("pilot/", views.pilot, name="pilot"),
    path("access/<slug:token>/", views.access, name="access"),
    path("listings/", views.dashboard, name="dashboard"),
    path("sign-out/", views.sign_out, name="sign_out"),
    path("checkout/<uuid:pk>/", views.start_checkout, name="checkout"),
    path("billing/<uuid:pk>/", views.portal, name="portal"),
    path("stripe/webhook/", views.stripe_webhook, name="webhook"),
]
