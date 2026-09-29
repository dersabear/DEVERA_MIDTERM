from django.contrib.auth import views as auth_views
from django.urls import path

from . import views


urlpatterns = [
    path("", views.chat_home, name="chat-home"),
    path("signup/", views.signup, name="signup"),
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("chats/new/", views.create_chat, name="create-chat"),
    path("chats/<uuid:chat_id>/", views.chat_detail, name="chat-detail"),
    path("chats/<uuid:chat_id>/generate/", views.generate, name="generate"),
    path("chats/<uuid:chat_id>/rename/", views.rename_chat, name="rename-chat"),
    path("chats/<uuid:chat_id>/instructions/", views.update_chat_instructions, name="chat-instructions"),
    path("chats/<uuid:chat_id>/archive/", views.archive_chat, name="archive-chat"),
    path("chats/<uuid:chat_id>/delete/", views.delete_chat, name="delete-chat"),
    path("settings/", views.settings_view, name="settings"),
    path("settings/profile/", views.update_profile, name="update-profile"),
    path("settings/global-prompt/", views.update_global_prompt, name="global-prompt"),
    path("settings/memories/new/", views.save_memory, name="save-memory"),
    path("settings/memories/<int:memory_id>/edit/", views.save_memory, name="edit-memory"),
    path("settings/memories/<int:memory_id>/toggle/", views.toggle_memory, name="toggle-memory"),
    path("settings/memories/<int:memory_id>/delete/", views.delete_memory, name="delete-memory"),
    path("feedback/<int:message_id>/", views.submit_feedback, name="submit-feedback"),
    path("attachments/<int:attachment_id>/", views.download_attachment, name="download-attachment"),
]
