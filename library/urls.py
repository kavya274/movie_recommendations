"""My Movies, the library mutations and the auth pages."""

from django.urls import path

from . import views

app_name = "library"

urlpatterns = [
    path("my-movies/", views.my_movies, name="my_movies"),
    path("library/watched/<slug:slug>/", views.toggle_watched_view, name="toggle_watched"),
    path("library/watchlist/<slug:slug>/", views.toggle_watchlist_view, name="toggle_watchlist"),
    path("login/", views.login_view, name="login"),
    path("signup/", views.signup_view, name="signup"),
    path("logout/", views.logout_view, name="logout"),
]

api_urlpatterns = [
    path("me/", views.api_me, name="me"),
]
