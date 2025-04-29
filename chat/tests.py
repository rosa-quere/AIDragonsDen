from django.test import TestCase
from chat.models import Conversation, Message, Participant, Bot, User, SubTopic
from chat.strategies import mention, summarize, encourage, transition, resolve, chime_in, indirect
from chat.dialog_analyzer import update_sub_topics_status, extract_utterance_features, update_accumulative_summary, extract_participant_features
from django.utils import timezone
from datetime import timedelta
import time

class StrategyTestCase(TestCase):

    def setUp(self):
        """Set up a conversation, participants, and bots for testing."""
        self.conversation = Conversation.objects.create()

        self.user_active = User.objects.create(username="active")
        self.user_silent = User.objects.create(username="silent")
        self.user = Participant.objects.create(participant_type="user", user=self.user_active)
        self.silent_user = Participant.objects.create(participant_type="user", user=self.user_silent)
        self.bot = Bot.objects.create(name="TestBot")
        self.bot_participant = Participant.objects.create(participant_type="bot", bot=self.bot)

        self.conversation.participants.add(self.user, self.bot_participant, self.silent_user)

    def test_mention(self):
        """Test if the mention strategy is correctly triggered when a bot is mentioned."""
        Message.objects.create(conversation=self.conversation, participant=self.user, message="@TestBot Hello!")

        response = mention(self.conversation)

        self.assertIsInstance(response, dict)
        self.assertIn(self.bot, response.keys())
        
    def test_indirect(self):
        """Test if the indirect strategy is correctly triggered when an indirect question is asked."""
        self.extra_bot = Participant.objects.create(participant_type="bot", bot=Bot.objects.create(name="ExtraBot"))
        self.conversation.participants.add(self.extra_bot)
        Message.objects.create(conversation=self.conversation, participant=self.user, message="What does everyone think about AI?")
        
        response = indirect(self.conversation)
        
        self.assertIsInstance(response, dict)
        self.assertIn(self.bot, response.keys())
        self.assertIn(self.extra_bot.bot, response.keys())

    def test_summarize(self):
        """Test Initiative Summarization when enough participants are active."""
        for i in range(5):
            Message.objects.create(conversation=self.conversation, participant=self.user, message=f"Sub Topic 1: message {i}")
            Message.objects.create(conversation=self.conversation, participant=self.user, message=f"Sub Topic 2: message {i}")

        response = summarize(self.conversation)

        self.assertIsInstance(response, dict)
        summary_message = response.values()[0]
        self.assertIn(self.bot, response.keys())
        self.assertIsNotNone(summary_message, "A summary message should be generated.")
        self.assertIn("summary", summary_message.lower(), "Summary should be present in the generated message.")
        self.assertLessEqual(abs(self.conversation.summary_update_date - timezone.now()), timedelta(seconds=1)
)

    def test_encourage(self):
        """Test Participation Encouragement by identifying lurkers and encouraging them."""
        Message.objects.create(conversation=self.conversation, participant=self.silent_user, message="Hi")
        for i in range(10):
            Message.objects.create(conversation=self.conversation, participant=self.user, message=f"Hello {i}, im a cool bot.")
        
        response = encourage(self.conversation)

        self.assertIsInstance(response, dict)
        encouragement_message = response.values()[0]
        self.assertIn(self.bot, response.keys())
        self.assertIsNotNone(encouragement_message, "An encouragement message should be generated.")
        self.assertIn("silent", encouragement_message.lower(), "Encouragement should be in message.")

    def test_transition(self):
        """Test Sub-topic Transition when the current topic is well-discussed."""
        for i in range(10):
            Message.objects.create(conversation=self.conversation, participant=self.user, message=f"Topic discussion {i}")

        update_sub_topics_status(self.conversation)
        response = transition(self.conversation)

        self.assertIsInstance(response, dict)
        transition_message = response.values()[0]
        self.assertIn(self.bot, response.keys())
        self.assertIsNotNone(transition_message, "A sub-topic transition message should be generated.")
        n_topics = len(self.conversation.sub_topics.all())
        update_sub_topics_status(self.conversation)
        self.assertEqual(len(self.conversation.sub_topics.all()), n_topics + 1)

    def test_resolve(self):
        """Test Conflict Resolution when a topic has stagnated in discussion."""
        for i in range(5):
            Message.objects.create(conversation=self.conversation, participant=self.user, message="I disagree!")

        response = resolve(self.conversation)
        
        self.assertIsInstance(response, dict)
        resolution_message = response.values()[0]
        self.assertIn(self.bot, response.keys())
        self.assertIsNotNone(resolution_message, "A conflict resolution message should be generated.")

    def test_chime_in_silence(self):
        """Test Chime-in strategy when conversation goes silent."""
        Message.objects.create(conversation=self.conversation, participant=self.user, message="Hello!")
        time.sleep(50)
        chime_in(self.conversation)

        chime_message = self.conversation.messages.order_by("timestamp").last()
        self.assertIsNotNone(chime_message, "A chime-in message should be generated.")

    def test_chime_in_repetition(self):
        """Test Chime-in strategy when conversation is repetitive."""
        Message.objects.create(conversation=self.conversation, participant=self.user, message="Repeat")
        Message.objects.create(conversation=self.conversation, participant=self.user, message="Repeat")
        Message.objects.create(conversation=self.conversation, participant=self.user, message="Repeat")

        response = chime_in(self.conversation)
        
        self.assertIsInstance(response, dict)
        chime_message = response.values()[0]
        self.assertIn(self.bot, response.keys())
        self.assertIsNotNone(chime_message, "A chime-in message should be generated.")
        #self.assertIn("stuck", chime_message.message.lower(), "Chime-in message should suggest breaking repetition.")

class DialogAnalyzerTestCase(TestCase):
    def setUp(self):
        """Set up a conversation, participants, and bots for testing."""
        self.conversation = Conversation.objects.create()

        self.user_active = User.objects.create(username="active")
        self.user = Participant.objects.create(participant_type="user", user=self.user_active)
        self.bot = Bot.objects.create(name="TestBot")
        self.bot_participant = Participant.objects.create(participant_type="bot", bot=self.bot)

        self.conversation.participants.add(self.user, self.bot_participant)
    
    def test_update_sub_topics_status(self):
        """Test the periodical sub topic status update"""
        Message.objects.create(conversation=self.conversation, participant=self.user, message="Hello, let's discuss healthcare")
        Message.objects.create(conversation=self.conversation, participant=self.user, message="Let's now discuss politics")
        
        update_sub_topics_status(self.conversation)
        
        self.assertIn("healthcare", self.conversation.sub_topics.last().name.lower())
        self.assertEqual("Being Discussed", self.conversation.sub_topics.last().status)
        self.assertIn("politics", self.conversation.sub_topics.first().name.lower())
        self.assertEqual("Being Discussed", self.conversation.sub_topics.first().status)
    
    def test_extract_utterance_features(self):
        """Test the utterance features extraction"""
        Message.objects.create(conversation=self.conversation, participant=self.user, message="Hello, let's discuss healthcare")
        update_sub_topics_status(self.conversation)
        for i in range(8):
            Message.objects.create(conversation=self.conversation, participant=self.user, message="politics")
        update_sub_topics_status(self.conversation)
        
        topics = extract_utterance_features(self.conversation)
        
        self.assertEqual(topics.count(), 1)
        self.assertIn("politics", topics.first().name.lower())
        
    
    def test_update_accumulative_summary(self):
        """Test the periodical summary update"""
        Message.objects.create(conversation=self.conversation, participant=self.user, message="I think AI is great for society.")
        Message.objects.create(conversation=self.conversation, participant=self.bot_participant, message="I think free healthcare is great for society")
    
        update_accumulative_summary(self.conversation)
        
        self.assertIn("active", self.conversation.summary.lower())
        self.assertIn("TestBot", self.conversation.summary)
        self.assertIn("AI", self.conversation.summary)
        self.assertIn("healthcare", self.conversation.summary.lower())
    
    def test_extract_participant_features(self):
        """Test the participant features extraction"""
        Message.objects.create(conversation=self.conversation, participant=self.user, message="Hello")
        Message.objects.create(conversation=self.conversation, participant=self.bot_participant, message="Hello!")
        
        features = extract_participant_features(self.conversation)
        expected = {self.user: {'freq': 1, 'len': 5}, self.bot_participant: {'freq': 1, 'len': 6}}
        self.assertEqual(features, expected)