from django.urls import include, path

from chat import views

app_name = "chat"

urlpatterns = [
    path("", views.index, name="index"),
    path("user/", views.user, name="user"),
    path("chat/new/", views.chat_new, name="chat_new"),
    path("chat/clear/", views.chat_clear, name="chat_clear"),
    path("chat/<uuid:conversation_uuid>/", views.chat, name="chat"),
    path("<uuid:conversation_uuid>/", views.chat, name="chat"),
    path(
        "<uuid:conversation_uuid>/load_messages/",
        views.load_messages,
        name="load_messages",
    ),
    path(
        "<uuid:conversation_uuid>/send_message/",
        views.send_message,
        name="send_message",
    ),
    path(
        "chat/<uuid:conversation_uuid>/title",
        views.load_conversation_title,
        name="load_conversation_title",
    ),
    path('sidebar/conversations/', 
         views.load_sidebar_conversations, 
         name='load_sidebar_conversations'),
    path(
        "chat/<uuid:conversation_uuid>/manage_bots/",
        views.manage_bots_in_conversation,
        name="manage_bots_in_conversation",
    ),
    path(
        "chat/<uuid:conversation_uuid>/manage_strategies/",
        views.manage_strategies_for_conversation,
        name="manage_strategies_for_conversation",
    ),
    path("chat/<uuid:conversation_uuid>/delete/", views.chat_delete, name="chat_delete"),
    path("accounts/", include("django.contrib.auth.urls")),
    path("chat/<uuid:conversation_uuid>/setup/", views.setup_conversation, name="setup_conversation"),
    path("chat/<uuid:conversation_uuid>/bots/create/", views.create_bot, name="create_bot"),
    path('chat/<uuid:conversation_uuid>/invite', views.invite_users, name='invite_users'),
    path('chat/<uuid:conversation_uuid>/join/', views.join_conversation, name='join_conversation'),
    path('chat/<uuid:conversation_uuid>/manage_settings/', views.manage_settings, name='manage_settings'),
    path('chat/<uuid:conversation_uuid>/settings/create/', views.create_settings, name="create_settings"),
    path('chat/<uuid:conversation_uuid>/finalize/', views.finalize_conversation_setup, name='finalize_conversation_setup'),
    path("chat/<uuid:conversation_uuid>/generate_segments/", views.generate_segments, name="generate_segments"),
]
