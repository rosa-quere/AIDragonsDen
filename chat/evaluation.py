import logging
import numpy as np

logger = logging.getLogger(__name__)

def engt_words_conv(conversation):
    """Average number of words exchanged per conversation"""
    messages = conversation.messages.filter(conversation=conversation).include(participant_type="bot")
    word_count = [len(msg.message.split()) for msg in messages]
    return np.sum(word_count)

def engt_words_utt(conversation):
    """Average number of words per utterance """
    messages = conversation.messages.filter(conversation=conversation).include(participant_type="bot")
    word_count = [len(msg.message.split()) for msg in messages]
    return np.mean(word_count)

def evenness(conversation):
    """Evenness is assessed by calculating the sample standard deviation 
    (STD) of the word count input by each participant, expressed as a percentage of the mean."""
    word_counts = {}
    messages = conversation.messages.filter(conversation=conversation)
    for msg in messages:
        participant = msg.participant
        if not participant:
            continue
        word_counts.setdefault(participant.id, 0)
        word_counts[participant.id] += len(msg.message.split())
    counts = list(word_counts.values())
    if not counts or np.mean(counts) == 0:
        return 0.0

    std = np.std(counts, ddof=1)
    mean = np.mean(counts)

    evenness = (std / mean) * 100
    return evenness
    

def consensus(conversation):
    """The consensus is obtained from the number of agreements reached over the total number of tasks."""
    pass
