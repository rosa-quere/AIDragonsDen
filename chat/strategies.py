import logging
import numpy as np

from django.conf import settings
from django.utils import timezone
from chat.bot import generate_message
from chat.helpers import detect_mention, get_last_active_bot, detect_question, check_waiting, detect_human_mention, get_random_bot
from chat.dialog_analyzer import extract_utterance_features, extract_participant_features, get_active_participants
from chat.models import Message, Conversation, Strategy
from datetime import datetime
import random

logger = logging.getLogger(__name__)

def mention(conversation):
    bots = [participant.bot for participant in conversation.participants.filter(participant_type="bot")]
    random.shuffle(bots)
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
    if not last_message:
        return False
    
    bots = [participant.bot for participant in conversation.participants.filter(participant_type="bot")]
    random.shuffle(bots)
    answers = {}
    
    if detect_human_mention(last_message):
        logger.info(f"[INFO] Human Mention detected, not bot turn")
        return False
    
    if detect_question(last_message):
        if last_message.participant.bot:
            bots.remove(last_message.participant.bot)
        for bot in bots[:settings.MAX_INDIRECT_ANSWERS]:
            response = generate_message(conversation, bot, "indirect")
            if response:
                answers[bot] = response
        return answers if answers else False
    if last_message.participant.user:
        bot = random.choice(bots)
        response = generate_message(conversation, bot, "indirect")
        if response:
            answers[bot] = response
            return answers
    return False

def chime_in_silence(conversation):
    logger.info("[INFO] Chime-in triggered due to extended silence.")
    bot = get_random_bot(conversation)
    generate_message(conversation, bot, "chime_in_silence", override_turn=True, post=True)
    
def fallback_chime(conversation_id, start_time):
    start_time = datetime.fromisoformat(start_time)
    conversation = Conversation.objects.get(id=conversation_id)
    latest_message = conversation.messages.order_by("timestamp").last()
    if latest_message and latest_message.timestamp >= start_time:
        logger.info(f"[INFO] New message detected, aborting chime")
        return
    elif detect_human_mention(latest_message):
        logger.info(f"[INFO] Human Mention detected, aborting chime")
        return
    elif conversation.messages.all().count() >=2 and latest_message.participant.bot and len(set([msg.participant for msg in conversation.messages.order_by("-timestamp")[:2]]))==1:
        logger.info(f"[INFO] Already Chimed in Silence, aborting chime")
        return
    chime_in_silence(conversation)
    
def summarize(conversation):
    """
    Creates a take-home summary if enough active participants have joined discussions since the last trigger.
    """
    # Get active participants who have contributed messages since the last summary
    active_participants = get_active_participants(conversation, conversation.summary_posted_date)

    if len(active_participants) - conversation.count_old_participants >= settings.ACTIVE_PARTICIPANT_THRESHOLD:
        logger.info(f"[INFO] Initiative Summarization triggered with {len(active_participants)} active participants.")

        conversation.summary_posted_date = conversation.messages.latest("timestamp").timestamp
        conversation.count_old_participants = len(active_participants)
        conversation.save()

        logger.info(f"[INFO] Updated conversation summary.")
        return {"summary": conversation.summary}
    
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
    strat_object = Strategy.objects.get(name="Encourage")
    
    for user, stats in participant_stats.items():
        freq = stats['freq']
        length = stats['len']
        if (freq < avg_freq - settings.LURKER_THRESHOLD_RATIO * freq_variance and 
           length < avg_len - settings.LURKER_THRESHOLD_RATIO * len_variance):
            conversation_messages = Message.objects.filter(conversation=conversation).order_by("-timestamp")[:N]
            recent_participation = [msg for msg in conversation_messages if msg.participant.user]
            if len(recent_participation) < settings.LURKER_THRESHOLD_COUNT:
                lurkers.append(user.user.username if user.user else user.bot.name)

    if lurkers and check_waiting(conversation, strat_object.triggered_at):
        logger.info(f"[INFO] Encouraging lurkers: {[user.user.username if user.user else user.bot.name for user in lurkers]}")
        strat_object.triggered_at = timezone.now()
        strat_object.save()
        return {"lurkers": ", ".join(lurkers)}
    
    return False
    
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
    strat_object = Strategy.objects.get(name="Transition")
    
    # Check if the sub-topic is well-discussed or losing interest
    if (extract_utterance_features(conversation).count()==0 or active_ratio <= settings.INTEREST_THRESHOLD) and check_waiting(conversation, strat_object.triggered_at):
        logger.info(f"[INFO] Transitioning to new sub-topic")
        strat_object.triggered_at = timezone.now()
        strat_object.save()
        return True
    
    return False

def resolve(conversation):
    """
    Helps users reach a consensus in a timely manner, thereby providing an efficient discussion procedure
    """
    # Check if stagnation occurred
    recent_messages = list(conversation.messages.order_by("-timestamp")[:settings.STAGNATION_PERIOD])
    if len(recent_messages) < settings.STAGNATION_PERIOD:
        return False
    earliest_timestamp = recent_messages[-1].timestamp
    strat_object = Strategy.objects.get(name="Resolve")
    
    if not conversation.sub_topics.filter(status_updated_at__gt=earliest_timestamp).exists() and check_waiting(conversation, strat_object.triggered_at):
        logger.info("[INFO] Conflict detected. Suggesting resolution.")
        strat_object.triggered_at = timezone.now()
        strat_object.save()
        return True
        
    return False

def chime_in(conversation):
    """
    Automatically chimes in to enhance conversation depth by:
    - Providing insights
    - Addressing unresolved issues
    - Advancing stuck scenarios
    Triggered by semantic Factor: Activated when conversation gets stuck (repetitive or unresolved issues).
    """
    messages_count = conversation.messages.count()
    if messages_count >= settings.REPETITION_THRESHOLD:
        last_messages = conversation.messages.order_by("-timestamp")[:settings.REPETITION_THRESHOLD]
        if len(set(msg.message for msg in last_messages)) == 1:
            logger.info("[INFO] Chime-in triggered due to repetitive conversation.")
            return True
    return False