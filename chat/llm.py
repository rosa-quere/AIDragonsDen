import logging
import time

#import openai
import mistralai
import re
from django.conf import settings
from django.utils import timezone

from chat.models import LLMRequest, SubTopic
from chat.prompt_templates import prompts

logger = logging.getLogger(__name__)


def prompt_llm_messages(
    messages,
    model=settings.LLM["mistral_basic_model"],
    response_format=None,
    temperature=0.8,
):
    client = mistralai.Mistral(api_key=settings.MISTRAL_API_KEY)
    max_retries = settings.MAX_RETRIES
    retry_delay = settings.RETRY_DELAY
    for attempt in range(1, max_retries + 1):
        try:
            response = client.chat.complete(
                model=settings.LLM["mistral_basic_model"],
                temperature=temperature,
                messages=messages,
                response_format=response_format,
            )

            bot_response = response.choices[0].message.content
            print(f'[LLM] Bot response: {bot_response}')
            # We store the last prompt/message
            LLMRequest.objects.create(
                model=model,
                temperature=temperature,
                request_type="llm_messages",
                prompt=messages[-1]["content"],
                response=bot_response,
                total_tokens=response.usage.total_tokens,
                completion_tokens=response.usage.completion_tokens,
            )
            return bot_response

        except mistralai.models.SDKError as e:
            if "429" in str(e) or "Too Many Requests" in str(e):
                logger.warning(f"[{attempt}/{max_retries}] Rate limit hit. Retrying in {retry_delay}s...")
                if attempt < max_retries:
                    time.sleep(retry_delay)
                    continue
            logger.error(f"SDKError on attempt {attempt}: {e}")
            return False
        except Exception as e:
            if "database is locked" in str(e):
                logger.warning(f"[{attempt}/{max_retries}] Database locked. Retrying in {retry_delay}s...")
                if attempt < max_retries:
                    time.sleep(retry_delay)
                    continue
            logger.error(f"Unhandled exception during LLM request (attempt {attempt}): {e}")
            return False
    
    # If all retries failed
    logger.error("Failed to complete LLM prompt after all retries.")
    return False


def llm_conversation_title(conversation):
    try:
        conversation_text = "\n".join([msg.message for msg in conversation.messages.all()])

        messages = [
            {
                "role": "system",
                "name": "system",
                "content": prompts["conversation_summary"].format(conversation_text=conversation_text),
            }
        ]

        bot_response = prompt_llm_messages(messages)

        # Sanitized bot response with only ASCII characters
        bot_response_sanitized = bot_response
        bot_response_sanitized = bot_response_sanitized.replace('"', "")
        bot_response_sanitized = "".join([i if ord(i) < 128 else " " for i in bot_response_sanitized])

        conversation.title = bot_response_sanitized
        conversation.title_update_date = timezone.now()
        conversation.save()

        return bot_response_sanitized
    except Exception as e:
        logger.error(f"Error generating conversation title: {e}")
        return conversation

def llm_generate_segments(context, duration, format):
    try:
        messages = [
            {
                "role": "system",
                "name": "system",
                "content": prompts["generate_segments"].format(context=context, duration=duration, format=format),
            }
        ]

        bot_response = prompt_llm_messages(messages).strip()

        # Extract JSON block using regex
        json_match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", bot_response, re.DOTALL)
        if json_match:
            bot_response = json_match.group(1)
        
        return bot_response
        
    except Exception as e:
        logger.error(f"Error auto generating segments: {e}")
        return context
    
def llm_generate_subtopics(conversation):
    settings = conversation.settings
    try:
        messages = [
            {
                "role": "system",
                "name": "system",
                "content": prompts["generate_subtopics"].format(context=settings.context, segments=[segment.prompt for segment in settings.segments.all()]),
            }
        ]

        bot_response = prompt_llm_messages(messages)

        for topic in bot_response.split(","):
            if topic is None:
                continue
            sub_topic = SubTopic.objects.create(name=topic.lstrip(), status="Not Discussed", conversation=conversation)
            sub_topic.save()
            conversation.sub_topics.add(sub_topic)
            conversation.save()
            
        conversation.subtopics_updated_at = timezone.now()
        conversation.save()
        
    except Exception as e:
        logger.error(f"Error generating subtopics: {e}")
        return 