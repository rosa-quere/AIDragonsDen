import logging
import time
import numpy as np

from django.conf import settings
from django.core.cache import cache
from chat.bot import generate_message, generate_message_general
from chat.helpers import detect_mention, get_last_active_bot, detect_question
from chat.dialog_analyzer import extract_utterance_features, extract_participant_features, get_active_participants, update_sub_topics_status, update_accumulative_summary
from chat.models import Message

logger = logging.getLogger(__name__)

def mention(conversation):
    bots = [participant.bot for participant in conversation.participants.filter(participant_type="bot")]
    answers = {}
    
    for bot in bots:
        messages = conversation.messages.exclude(triggered_bots__id=bot.id).exclude(participant__bot__id=bot.id)
        mentionned_messaged = detect_mention(bot.name, messages)
        if mentionned_messaged:
            logger.info(f'[INFO] Mention detected: {bot.name}')
            for msg in mentionned_messaged:
                msg.triggered_bots.add(bot)
            response = generate_message(conversation, bot, "mention")
            if response and response.lower().strip()!="no" and response.lower().strip()!="no.": 
                answers[bot] = response
    return answers if answers else False
    

def indirect(conversation):
    """
    Replies to indirect questions i.e. without explicit mentions. Makes bots reply when general question is asked.
    """
    last_message = conversation.messages.order_by("timestamp").last()
    
    if detect_question(last_message, get_last_active_bot(conversation)):
        bots = [participant.bot for participant in conversation.participants.filter(participant_type="bot")]
        if last_message.participant.bot:
            bots.remove(last_message.participant.bot)
        answers = {}
        for bot in bots:
            response = generate_message(conversation, bot, "indirect")
            if response: 
                answers[bot] = response
        return answers if answers else False
    return False
        

def general(conversation):
    bots = [participant.bot for participant in conversation.participants.filter(participant_type="bot")]

    for bot in bots:
        generate_message_general(conversation, bot)
        time.sleep(5)

def summarize(conversation):
    """
    Creates a take-home summary if enough active participants have joined discussions since the last trigger.
    """
    # Get active participants who have contributed messages since the last summary
    active_participants = get_active_participants(conversation, conversation.summary_update_date)
    outcome_1 = update_sub_topics_status(conversation)
    outcome_2 = update_accumulative_summary(conversation)

    if outcome_1 is True and outcome_2 is True and len(active_participants) >= settings.ACTIVE_PARTICIPANT_THRESHOLD:
        logger.info(f"[INFO] Initiative Summarization triggered with {len(active_participants)} active participants.")
        bot = get_last_active_bot(conversation)

        # logger.info(f"[summarize] Generating a new message as {bot.name}")
        # Message.objects.create(
        #     conversation=conversation,
        #     participant=conversation.participants.get(bot__id=bot.id),
        #     message=conversation.summary,
        # )

        conversation.summary_update_date = conversation.messages.latest("timestamp").timestamp
        conversation.save()

        logger.info(f"[INFO] Updated conversation summary.")
        return {bot:conversation.summary}
    
    return False
        
def encourage(conversation):
    """
    Encourages less vocal participants (lurkers) to engage in the conversation.
    """
    participant_stats = extract_participant_features(conversation, context=settings.LONG_TERM_CONTEXT)
    if not participant_stats or len(participant_stats) < 2:
        return False
    # Compute overall frequency and length statistics
    all_frequencies = [stats['freq'] for stats in participant_stats.values()]
    all_lengths = [stats['len'] for stats in participant_stats.values()]
    avg_freq = np.mean(all_frequencies)
    avg_len = np.mean(all_lengths)
    
    # Compute variance-based threshold
    freq_variance = np.std(all_frequencies, ddof=1)
    len_variance = np.std(all_lengths, ddof=1)
    
    N = settings.SHORT_TERM_CONTEXT
    lurkers = []
    response = None
    for user, stats in participant_stats.items():
        freq = stats['freq']
        length = stats['len']
        if (freq < avg_freq - settings.LURKER_THRESHOLD_RATIO * freq_variance and 
           length < avg_len - settings.LURKER_THRESHOLD_RATIO * len_variance):
            conversation_messages = Message.objects.filter(conversation=conversation).order_by("-timestamp")[:N]
            recent_participation = [msg for msg in conversation_messages if msg.participant==user]
            if len(recent_participation) < settings.LURKER_THRESHOLD_COUNT:
                lurkers.append(user)

    if lurkers:
        logger.info(f"[INFO] Encouraging lurkers: {[user.user.username if user.user else user.bot.name for user in lurkers]}")
        bot = get_last_active_bot(conversation)
        response = generate_message(conversation, bot, "encourage", override_turn=True, lurkers=lurkers)
    
    return {bot:response} if response else False
    
def transition(conversation):
    """
    Introduces a new sub-topic when the current one is well-discussed or interest declines.
    """
    participant_stats = extract_participant_features(conversation)
    total_participants = len(get_active_participants(conversation))
    if not participant_stats or total_participants==0:
        return False
    
    active_participants = len(get_active_participants(conversation, settings.SHORT_TERM_CONTEXT))
    active_ratio = active_participants / total_participants
    response = None
    
    # Check if the sub-topic is well-discussed or losing interest
    if extract_utterance_features(conversation).count()==0 or active_ratio <= settings.INTEREST_THRESHOLD:
        logger.info(f"[INFO] Transitioning to new sub-topic")
        bot = get_last_active_bot(conversation)
        response = generate_message(conversation, bot, "transition", override_turn=True)
    
    return {bot:response} if response else False

def resolve(conversation):
    """
    Helps users reach a consensus in a timely manner, thereby providing an efficient discussion procedure
    """
    # Check if stagnation occurred
    recent_messages = list(conversation.messages.order_by("-timestamp")[:settings.STAGNATION_PERIOD])
    if len(recent_messages) < settings.STAGNATION_PERIOD:
        return False
    earliest_timestamp = recent_messages[-1].timestamp
    past_count = conversation.sub_topics.filter(status="well discussed", status_updated_at__lt=earliest_timestamp).count()
    current_count = conversation.sub_topics.filter(status="well discussed").count()
    response = None

    if current_count <= past_count:
        logger.info("[INFO] Conflict detected. Suggesting resolution.")
        bot = get_last_active_bot(conversation)
        response = generate_message(conversation, bot, "resolve", override_turn=True)
        
    return {bot:response} if response else False

def chime_in(conversation):
    """
    Automatically chimes in to enhance conversation depth by:
    - Providing insights
    - Addressing unresolved issues
    - Advancing stuck scenarios
    Triggered by semantic Factor: Activated when conversation gets stuck (repetitive or unresolved issues).
    """
    bot = get_last_active_bot(conversation)
    response = None

    messages_count = conversation.messages.count()
    if messages_count >= settings.REPETITION_THRESHOLD:
        last_messages = conversation.messages.order_by("-timestamp")[:settings.REPETITION_THRESHOLD]
        if len(set(msg.message for msg in last_messages)) == 1:
            logger.info("[INFO] Chime-in triggered due to repetitive conversation.")
            response = generate_message(conversation, bot, "chime_in_repetition")
            return {bot:response} if response else False
    return False

def chime_in_silence(conversation):
    logger.info("[INFO] Chime-in triggered due to extended silence.")
    bot = get_last_active_bot(conversation)
    generate_message(conversation, bot, "chime_in_silence", override_turn=True, post=True)
    
def fallback_chime(conversation, start_time):
    latest_message = conversation.messages.order_by("timestamp").last()
    if latest_message and latest_message.timestamp >= start_time:
        logger.info(f"[INFO] New message detected, aborting chime")
        return

    chime_in_silence(conversation)

def clear_fallback_task(task):
    conversation_id = task.args[0]
    cache_key = f"fallback_chime_{conversation_id}"
    cache.delete(cache_key)
    logger.info(f"[INFO] Cleared fallback task cache for conversation {conversation_id}")