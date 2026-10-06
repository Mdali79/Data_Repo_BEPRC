from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("signup/", views.signup_view, name="signup"),
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html", redirect_authenticated_user=True), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),

    # Super admin only
    path("manage/users/", views.user_list_view, name="user_list"),
    path("manage/users/new/", views.user_create_view, name="user_create"),
    path("manage/users/<int:pk>/", views.user_edit_view, name="user_edit"),
    path("manage/users/<int:pk>/toggle-active/", views.user_toggle_active_view, name="user_toggle_active"),
    path("manage/users/<int:pk>/delete/", views.user_delete_view, name="user_delete"),
    path("manage/roles/", views.role_list_view, name="role_list"),
    path("manage/roles/new/", views.role_edit_view, name="role_create"),
    path("manage/roles/<int:pk>/", views.role_edit_view, name="role_edit"),
    path("manage/roles/<int:pk>/delete/", views.role_delete_view, name="role_delete"),
]
