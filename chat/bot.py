import logging

from django.conf import settings

from chat.helpers import get_system_prompt, judge_bot_determination
from chat.llm import prompt_llm_messages
from chat.models import Message
from chat.prompt_templates import prompts

logger = logging.getLogger(__name__)


def check_turn(conversation, bot):
    messages = []

    for msg in conversation.messages.all():
        role = "user" if msg.participant.participant_type == "user" else "assistant"
        messages.append(
            {
                "role": role,
                "name": msg.participant.user.username if msg.participant.participant_type == "user" else msg.participant.bot.name,
                "content": msg.message,
            }
        )

    # Human goes first
    if len(messages) == 0:
        return False

    if len(messages) > 0:
        if messages[-1]["name"] == bot.name and not settings.DOUBLE_TEXTING:
            logger.info("Bot has already replied")
            return False

        # Make sure the user has replied enough times; but allow answers after a user has replied
        human_replies = [msg for msg in messages[-10:] if msg["role"] == "user"]
        if len(human_replies) < settings.MIN_HUMAN_REPLIES_LAST_10 and len(messages) > settings.NEW_CHAT_GRACE and messages[-1]["role"] != "user":
            logger.info(f"User has not replied enough times ({len(human_replies)} < {settings.MIN_HUMAN_REPLIES_LAST_10})")
            return False

        bot_replies = [msg for msg in messages[-10:] if msg["name"] == bot.name]
        if len(bot_replies) >= settings.MAX_THIS_BOT_REPLIES_LAST_10:
            logger.info(f"Bot has replied too many times ({len(bot_replies)} >= {settings.MAX_THIS_BOT_REPLIES_LAST_10})")
            return False

    return True


def check_message(new_message, bot):
    # Self-Referential @mention
    if f"@{bot.name.lower()}" in new_message.lower().strip():
        logger.info("Self-referential response")
        return False
    else:
        return True

def set_up(conversation, bot, override_turn=False):
    if not override_turn:
        if not check_turn(conversation, bot):
            return False

    # Prepare the system message using the bot's prompt
    system_prompt = get_system_prompt(conversation, bot)

    messages = [{"role": "system", "name": "system", "content": system_prompt}]

    # Retrieve all messages for the conversation ordered by timestamp
    conversation_messages = Message.objects.filter(conversation=conversation).order_by("timestamp")

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
    return messages

def generate_best_message(conversation, bot, answers):
    # Convert each message into the format required by LLM
    messages = []
    for msg in answers:
        role = "assistant"
        messages.append(
            {
                "role": role,
                "name": msg.participant.bot.name,
                "content": msg,
            }
        )
    if messages is False:
        return False
    messages.append(
        {
            "role": "user",
            "name": "System",
            "content": prompts["combine_answers"],
        }
    )
    bot_response = prompt_llm_messages(messages, model=bot.model, temperature=bot.temperature)
    if not check_message(bot_response, bot):
        logger.info(f"[{"combine_answers"}] Failed 'check_message' for {bot.name}. Bot response: {bot_response}")
        return False
    logger.info(f"[{"combine_answers"}] Generating a new message as {bot.name}")
    Message.objects.create(
        conversation=conversation,
        participant=conversation.participants.get(bot__id=bot.id),
        message=bot_response,
    )

def generate_message(conversation, bot, strategy, override_turn=False, **kwargs):
    messages = set_up(conversation, bot, override_turn)
    if messages is False:
        return False
    messages.append(
        {
            "role": "user",
            "name": "System",
            "content": prompts[strategy].format(bot_name=bot.name, **kwargs),
        }
    )
    bot_response = prompt_llm_messages(messages, model=bot.model, temperature=bot.temperature)
    if not check_message(bot_response, bot):
        logger.info(f"[{strategy}] Failed 'check_message' for {bot.name}. Bot response: {bot_response}")
        return False
    #logger.info(f"[{strategy}] Generating a new message as {bot.name}")
    # Message.objects.create(
    #     conversation=conversation,
    #     participant=conversation.participants.get(bot__id=bot.id),
    #     message=bot_response,
    # )
    return bot_response

def generate_message_summarize(conversation, bot):
    messages = set_up(conversation, bot)
    if messages is False:
        return False
    messages.append(
            {
                "role": "user",
                "name": "System",
                "content": prompts["summarize"].format(bot_name=bot.name),
            }
        )

    bot_response = prompt_llm_messages(messages, model=bot.model, temperature=bot.temperature)

    if not check_message(bot_response, bot):
        logger.info(f"[Summary] Failed 'check_message' for {bot.name}. Bot response: {bot_response}")
        return False

    logger.info(f"[Summary] Generating a new message as {bot.name}")
    return bot_response
    # Message.objects.create(
    #     conversation=conversation,
    #     participant=conversation.participants.get(bot__id=bot.id),
    #     message=bot_response,
    # )

def generate_message_general(conversation, bot):
    if not check_turn(conversation, bot):
        return False

    # Prepare the system message using the bot's prompt
    system_prompt = get_system_prompt(conversation, bot)

    messages = [{"role": "system", "name": "system", "content": system_prompt}]

    # Retrieve all messages for the conversation ordered by timestamp
    conversation_messages = Message.objects.filter(conversation=conversation).order_by("timestamp")

    # Convert each message into the format required by OpenAI
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
            "content": prompts["general_determine"].format(bot_name=bot.name),
        }
    )

    # No bot specific temperature for this prompt
    bot_response = prompt_llm_messages(messages, model=bot.model)
    logger.debug(f'Bot response: {bot_response}')

    if judge_bot_determination(bot_response):
        messages.pop()

        messages.append(
            {
                "role": "user",
                "name": "System",
                "content": prompts["general_generate"].format(bot_name=bot.name),
            }
        )

        bot_response = prompt_llm_messages(messages, model=bot.model, temperature=bot.temperature)

        if not check_message(bot_response, bot):
            logger.info(f"[Mention] Failed 'check_message' for {bot.name}. Bot response: {bot_response}")
            return False

        logger.info(f"[General] Generating a new message as {bot.name}")
        Message.objects.create(
            conversation=conversation,
            participant=conversation.participants.get(bot__id=bot.id),
            message=bot_response,
        )
    else:
        logger.info(f"[General] Not generating a new message as {bot.name}. Bot response: {bot_response}")
