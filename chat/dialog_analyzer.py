import logging

from django.conf import settings

from chat.llm import prompt_llm_messages
from chat.models import Message, SubTopic
from chat.prompt_templates import prompts
from collections import Counter
from chat.helpers import get_last_active_bot
from datetime import datetime

logger = logging.getLogger(__name__)

def update_sub_topics_status(conversation):
    """
    Categorizes sub-topics as Not Discussed, Being Discussed, or Well Discussed.
    """
    # Prepare the system message using MUCA's prompt
    system_prompt = prompts["muca"]
    
    messages = [{"role": "system", "name": "system", "content": system_prompt}]

    # Retrieve N messages for the conversation ordered by timestamp
    N = settings.SHORT_TERM_CONTEXT
    conversation_messages = conversation.messages.order_by("-timestamp")[:N]

    # Convert each message into the format required by LLM
    for msg in conversation_messages:
        role = "user" if msg.participant.participant_type == "user" else "assistant"
        messages.append(
            {
                "role": role,
                "name": msg.participant.user.username if msg.participant.participant_type == "user" else msg.participant.bot.name,
                "content": msg.message,
            }
        )

    messages.append(
        {
            "role": "user",
            "name": "System",
            "content": prompts["sub_topics"].format(list_of_sub_topics=conversation.sub_topics.all()),
        }
    )
    bot_response = prompt_llm_messages(messages, model=settings.MUCA["model"], temperature=settings.MUCA["temperature"])
    
    if bot_response is False:
        return False
    else:
        for pair in bot_response.split("\n"):
            if pair is None:
                continue
            ts = pair.split(",")
            if len(ts) != 2:
                continue
            sub_topic, created = SubTopic.objects.get_or_create(name=ts[0], conversation=conversation)
            sub_topic.status = ts[1].lstrip()
            sub_topic.save()
            if created:
                conversation.sub_topics.add(sub_topic)
        
        logger.info(f"[MUCA] Updating Sub-Topics and Statuses")
        return True

def extract_utterance_features(conversation):
    """
    Extracts currently being discussed sub-topics.
    """
    return conversation.sub_topics.all().filter(status="Being Discussed")

def update_accumulative_summary(conversation):
    """
    Updates user-specific summary across sub-topics.
    """
    messages = []
    bot = get_last_active_bot(conversation)
    participants = [p.user.username if p.user else p.bot.name for p in conversation.participants.all()]
    # Retrieve all messages for the conversation ordered by timestamp
    conversation_messages = conversation.messages.order_by("timestamp")

    # Convert each message into the format required by LLM
    for msg in conversation_messages:
        role = "user" if msg.participant.participant_type == "user" else "assistant"
        messages.append(
            {
                "role": role,
                "name": msg.participant.user.username if msg.participant.participant_type == "user" else msg.participant.bot.name,
                "content": msg.message,
            }
        )
    messages.append(
        {
            "role": "user",
            "name": "System",
            "content": prompts["summarize"].format(names=participants),
        }
    )
    bot_response = prompt_llm_messages(messages, model=bot.model, temperature=bot.temperature)
    if bot_response is False:
        return False
    else:
        conversation.summary = bot_response
        conversation.save()
        return True

def extract_participant_features(conversation, context=settings.SHORT_TERM_CONTEXT):
    """
    Extracts participants statistics like frequency and message length.
    """
    messages = conversation.messages.all().order_by("-timestamp")[:context]
    user_message_count = Counter()
    user_word_count = Counter()
    
    for msg in messages:
        user_message_count[msg.participant] += 1
        user_word_count[msg.participant] += len(msg.message)

    # Compile user statistics
    user_stats = {
        user: {
            "freq": user_message_count[user],
            "len": user_word_count[user],
        }
        for user in user_message_count
    }
    
    return user_stats

def get_active_participants(conversation, time=None):
    messages = conversation.messages.all()
    
    if time is None:
        return set(message.participant for message in messages)

    elif isinstance(time, datetime):
        if not messages or time <= messages.first().timestamp:
            return set(message.participant for message in messages)
        else:
            return set(
                message.participant for message in messages.filter(timestamp__gte=time)
            )

    elif isinstance(time, int):
        if time >= messages.count():
            return set(message.participant for message in messages)

        recent_messages = conversation.messages.all().order_by("-timestamp")[:time]
        return set(message.participant for message in recent_messages)

    else:
        raise ValueError("`time` must be None, a datetime object, or an integer.")
