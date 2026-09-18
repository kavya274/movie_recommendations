"""Catalog routes — pages first, then the read-only JSON API."""

from django.urls import path

from . import views

app_name = "catalog"

urlpatterns = [
    path("", views.home, name="home"),
    path("discover/", views.discover, name="discover"),
    path("search/", views.search, name="search"),
    path("movies/<slug:slug>/", views.movie_detail, name="movie_detail"),
]

api_urlpatterns = [
    path("movies/", views.api_movies, name="movies"),
    path("movies/<slug:slug>/", views.api_movie, name="movie"),
    path("genres/", views.api_genres, name="genres"),
    path("search/", views.api_search, name="search"),
    path("recommendations/", views.api_recommendations, name="recommendations"),
    path("chat/", views.api_chat, name="chat"),
]
