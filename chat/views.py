from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.contrib.auth import login
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST
from django_q.models import Schedule
from django_q.tasks import schedule
from django.utils import timezone
from django.forms import modelformset_factory

from chat.forms import ManageBotsForm, ManageStrategiesForm, CreateBotForm, CreateSegmentForm, ManageSettingsForm, CreateSettingsForm
from chat.llm import llm_generate_subtopics, llm_generate_segments
from chat.models import Conversation, Message, Participant, User, Strategy, Segment, Settings
from chat.evaluation import get_metrics
from chat.helpers import render_summary

import json
import markdown
from django.utils.safestring import mark_safe

@login_required
def index(request):
    context = {
        "conversations": Conversation.objects.all(),
        "version": settings.VERSION,
    }

    return render(request, "chat/index.html", context)


@login_required
def chat_new(request):
    # Create a new conversation
    conversation = Conversation.objects.create()

    # Create a participant for the logged-in user
    participant, _ = Participant.objects.get_or_create(participant_type="user", user=request.user)
    conversation.participants.add(participant)
    
    # Add by default all strategies
    for strat in Strategy.objects.all():
        conversation.strategies.add(strat)
    
    schedule("chat.tasks.update_conversation_title",
        conversation.id,
        schedule_type="I",
        minutes=2,
        name=f"update_conversation_title_{conversation.id}",
    )
    
    # schedule("chat.tasks.update_conversation_subtopics",
    #     conversation.id,
    #     schedule_type="I",
    #     minutes=0.25,
    #     name=f"update_conversation_subtopics_{conversation.id}",
    # )
    
    schedule("chat.tasks.update_conversation_summary",
        conversation.id,
        schedule_type="I",
        minutes=2,
        name=f"update_conversation_summary_{conversation.id}",
    )
    
    schedule("chat.tasks.update_evaluation_metrics",
        conversation.id,
        schedule_type="I",
        minutes=5,
        name=f"update_evaluation_metrics_{conversation.id}",
    )
    
    return redirect("chat:setup_conversation", conversation_uuid=conversation.uuid)

@login_required
def setup_conversation(request, conversation_uuid):
    conversation = get_object_or_404(Conversation, uuid=conversation_uuid)
    context = {
        "conversation": conversation,
        "version": settings.VERSION,
    }
    return render(request, "chat/setup_conversation.html", context)

@login_required
def finalize_conversation_setup(request, conversation_uuid):
    conversation = get_object_or_404(Conversation, uuid=conversation_uuid)

    if conversation.count_old_participants==0:
        # Update creation timestamp and count of participants
        conversation.created_at = timezone.now()
        conversation.count_old_participants = conversation.participants.count()
        conversation.save()

    return redirect('chat:chat', conversation_uuid=conversation.uuid)

@login_required
def chat(request, conversation_uuid=False):
    # Fetch the conversation instance based on the UUID provided as a query parameter
    conversation = get_object_or_404(Conversation, uuid=conversation_uuid)

    # Retrieve all participants (both users and bots) from the conversation
    participants = conversation.participants.select_related("user", "bot").all()

    # Retrieve all messages for the conversation
    messages = Message.objects.filter(conversation=conversation).select_related("participant__user", "participant__bot").order_by("timestamp")

    # Create the context to pass to the template
    context = {
        "conversations": Conversation.objects.all(),
        "conversation": conversation,
        "messages": messages,
        "participants": participants,
        "version": settings.VERSION,
    }

    return render(request, "chat/chat.html", context)


@login_required
def user(request):
    context = {
        "conversations": Conversation.objects.all(),
        "version": settings.VERSION,
    }

    return render(request, "chat/user.html", context)


@login_required
def load_messages(request, conversation_uuid):
    conversation = get_object_or_404(Conversation, uuid=conversation_uuid)
    messages = Message.objects.filter(conversation=conversation).select_related("participant__user", "participant__bot").order_by("timestamp")
    return render(request, "chat/partials/messages.html", {"messages": messages})


@login_required
def load_conversation_title(request, conversation_uuid):
    conversation = get_object_or_404(Conversation, uuid=conversation_uuid)
    #return HttpResponse(llm_conversation_title(conversation))
    return render(request, "chat/partials/conversation_title.html", {"conversation": conversation})

@login_required
def load_sidebar_conversations(request):
    conversations = Conversation.objects.all().order_by('-creation_date')  # Adjust queryset as needed
    return render(request, 'chat/partials/sidebar_conversations.html', {'conversations': conversations})

@login_required
def load_sidebar_metrics(request, conversation_uuid):
    conversation = get_object_or_404(Conversation, uuid=conversation_uuid)
    rendered_summary = mark_safe(markdown.markdown(conversation.summary)) if conversation.summary else None
    context = {
        "conversation": conversation,
        "metrics": get_metrics(conversation),
        "subtopics": conversation.sub_topics.all(),
        #"summary": render_summary(conversation.summary),
        "summary": rendered_summary,
    }
    return render(request, "chat/partials/metrics.html", context)


@login_required
@require_http_methods(["POST"])
def send_message(request, conversation_uuid):
    conversation = get_object_or_404(Conversation, uuid=conversation_uuid)
    participant = conversation.participants.filter(user=request.user).first()  # Assuming the logged-in user is the sender

    if participant and "message" in request.POST:
        message_content = request.POST["message"]
        Message.objects.create(conversation=conversation, participant=participant, message=message_content)

        # if conversation.triggers.filter(name="mention").exists():
        #     mention(conversation)

    # Return updated messages list
    messages = Message.objects.filter(conversation=conversation).select_related("participant__user", "participant__bot").order_by("timestamp")
    return render(request, "chat/partials/messages.html", {"messages": messages})


@login_required
@require_http_methods(["GET", "POST"])
def manage_bots_in_conversation(request, conversation_uuid):
    conversation = get_object_or_404(Conversation, uuid=conversation_uuid)

    if request.method == "POST":
        form = ManageBotsForm(request.POST)
        if form.is_valid():
            current_bots = conversation.participants.filter(participant_type="bot")
            selected_bots = form.cleaned_data["bots"]

            removed_bots = current_bots.exclude(bot__in=selected_bots)

            for removed_bot in removed_bots:
                conversation.participants.remove(removed_bot)

            for bot in selected_bots:
                participant, created = Participant.objects.get_or_create(participant_type="bot", bot=bot)
                conversation.participants.add(participant)

            return redirect("chat:setup_conversation", conversation_uuid=conversation.uuid)
    else:
        form = ManageBotsForm(initial={"bots": conversation.participants.filter(participant_type="bot").values_list("bot", flat=True)})

    # Create the context to pass to the template
    context = {
        "conversations": Conversation.objects.all(),
        "form": form,
        "conversation": conversation,
        "version": settings.VERSION,
    }

    return render(request, "chat/manage_bots.html", context)

@login_required
@require_http_methods(["GET", "POST"])
def create_bot(request, conversation_uuid):
    conversation = get_object_or_404(Conversation, uuid=conversation_uuid)

    if request.method == "POST":
        form = CreateBotForm(request.POST)
        if form.is_valid():
            new_bot = form.save()

            # Add the new bot to the conversation
            participant, _ = Participant.objects.get_or_create(participant_type="bot", bot=new_bot)
            conversation.participants.add(participant)

            return redirect("chat:manage_bots_in_conversation", conversation_uuid=conversation_uuid)
    else:
        form = CreateBotForm()

    context = {
        "conversation": conversation,
        "form": form,
        "version": settings.VERSION,
    }

    return render(request, "chat/create_bot.html", context)

@login_required
@require_http_methods(["GET", "POST"])
def manage_strategies_for_conversation(request, conversation_uuid):
    conversation = get_object_or_404(Conversation, uuid=conversation_uuid)

    if request.method == "POST":
        form = ManageStrategiesForm(request.POST)
        if form.is_valid():
            current_strategies = conversation.strategies.all()
            selected_strategies = form.cleaned_data["strategies"]

            removed_strategies = current_strategies.exclude(id__in=selected_strategies)

            for removed_strategies in removed_strategies:
                conversation.strategies.remove(removed_strategies)

            for strategy in selected_strategies:
                conversation.strategies.add(strategy)

            return redirect("chat:setup_conversation", conversation_uuid=conversation.uuid)
    else:
        form = ManageStrategiesForm(initial={"strategies": conversation.strategies.all().values_list(flat=True)})

    # Create the context to pass to the template
    context = {
        "conversations": Conversation.objects.all(),
        "form": form,
        "conversation": conversation,
        "version": settings.VERSION,
    }

    return render(request, "chat/manage_strategies.html", context)

@login_required
@require_http_methods(["GET", "POST"])
def manage_settings(request, conversation_uuid):
    conversation = get_object_or_404(Conversation, uuid=conversation_uuid)

    if request.method == "POST":
        form = ManageSettingsForm(request.POST)
        if form.is_valid():
            settings_name = form.cleaned_data["settings"]
            print(settings_name)

            settings_object = Settings.objects.get(name=settings_name)
            conversation.settings = settings_object
            conversation.save()
            llm_generate_subtopics(conversation)

            return redirect("chat:setup_conversation", conversation_uuid=conversation.uuid)
    else:
        form = ManageSettingsForm(initial={"settings": conversation.settings})

    # Create the context to pass to the template
    context = {
        "conversations": Conversation.objects.all(),
        "form": form,
        "conversation": conversation,
        "version": settings.VERSION,
    }

    return render(request, "chat/manage_settings.html", context)

@login_required
@require_http_methods(["GET", "POST"])
def create_settings(request, conversation_uuid):
    conversation = get_object_or_404(Conversation, uuid=conversation_uuid)
    SegmentFormSet = modelformset_factory(Segment, form=CreateSegmentForm, extra=3)
    SegmentFormSetEmpty = modelformset_factory(Segment, form=CreateSegmentForm, extra=0)
    settings_form = CreateSettingsForm(request.POST or None)
    segment_formset = None

    if request.method == "POST":
        if 'generate_segments' in request.POST:
            segment_data = generate_segments(request)
            segment_formset = SegmentFormSet(queryset=Segment.objects.none(), initial=segment_data)
        elif 'save_all' in request.POST:
            segment_formset = SegmentFormSet(request.POST, queryset=Segment.objects.none())
            if settings_form.is_valid() and segment_formset.is_valid():
                conv_settings = settings_form.save()
                segments = segment_formset.save(commit=False)
                for segment in segments:
                    segment.settings = conv_settings
                    segment.save()
                conversation.settings = conv_settings
                conversation.save()
                llm_generate_subtopics(conversation)
            
                return redirect("chat:setup_conversation", conversation_uuid=conversation.uuid)
    else:
        settings_form = CreateSettingsForm()
        segment_formset = SegmentFormSetEmpty(queryset=Segment.objects.none())
    
    context = {
        "conversation": conversation,
        "form": settings_form,
        'segment_formset': segment_formset,
        "version": settings.VERSION,
    }

    return render(request, "chat/create_settings.html", context)

@login_required
@require_POST
def generate_segments(request):
    context_text = request.POST.get("context", "").strip()
    duration_text = request.POST.get("duration", "").strip()

    if not context_text:
        return HttpResponseBadRequest("Context is required.")
    if not duration_text:
        return HttpResponseBadRequest("Duration is required.")

    segments_format = [{"name": "Introduction", "prompt": "Start with intros...", "duration_minutes": 5, "order": 0},
        {"name": "Main Discussion", "prompt": "Deep dive into the topic...", "duration_minutes": 15, "order": 1},
        {"name": "Wrap-up", "prompt": "Summarize and conclude", "duration_minutes...": 5, "order": 2}]
    
    segments_data = json.loads(llm_generate_segments(context_text, duration_text, segments_format))

    return segments_data

@login_required
def invite_users(request, conversation_uuid):
    conversation = get_object_or_404(Conversation, uuid=conversation_uuid)
    context = {
        "conversation": conversation,
        "invite_link": request.build_absolute_uri(conversation.invite_link),
    }
    return render(request, "chat/invite_users.html", context)


@login_required
def chat_clear(request):
    conversations = Conversation.objects.all()

    for conversation in conversations:
        Schedule.objects.filter(name=f"generate_messages_{conversation.uuid}").delete()
        
        # Remove and delete temporary participants and users
        temp_participants = conversation.participants.filter(is_temporary=True)
        for participant in temp_participants:
            if participant.user:
                participant.user.delete()
            participant.delete()
        
        # Cancel any previously scheduled task for this conversation
        tasks = Schedule.objects.filter(name__contains=conversation.id)
        if tasks:
            for task in tasks:
                task.delete()

        conversation.delete()

    return redirect("chat:index")


@login_required
def chat_delete(request, conversation_uuid):
    conversation = get_object_or_404(Conversation, uuid=conversation_uuid)
    Schedule.objects.filter(name=f"generate_messages_{conversation.uuid}").delete()
    
    # Remove and delete temporary participants and users
    temp_participants = conversation.participants.filter(is_temporary=True)
    for participant in temp_participants:
        if participant.user:
            participant.user.delete()
        participant.delete()
    
    # Cancel any previously scheduled task for this conversation
    tasks = Schedule.objects.filter(name__contains=conversation.id)
    if tasks:
        for task in tasks:
            task.delete()

    conversation.delete()

    return redirect("chat:index")

def join_conversation(request, conversation_uuid):
    conversation = get_object_or_404(Conversation, uuid=conversation_uuid)

    if request.method == 'POST':
        username = request.POST.get('username').strip()
        if not username:
            return render(request, 'join.html', {"error": "Username required", "conversation": conversation})
        
        # Check uniqueness within the conversation
        if conversation.participants.filter(user__username=username).exists():
            return render(request, "chat/join_conversation.html", {"error": "Username already taken in this conversation."})


        # Create a temporary user
        user_obj = User.objects.create(username=username)
        user_obj.set_unusable_password()
        user_obj.save()
        
        # Create and link the participant
        user = Participant.objects.create(
            user=user_obj,
            participant_type="user",
            is_temporary=True
        )

        # Add participant to conversation
        conversation.participants.add(user)
        
        user_obj.backend = 'django.contrib.auth.backends.ModelBackend'
        login(request, user_obj, backend=user_obj.backend)
        
        return redirect('chat:chat', conversation_uuid=conversation.uuid)

    return render(request, 'chat/join_conversation.html', {"conversation": conversation})