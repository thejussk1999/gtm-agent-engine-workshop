import unittest
from types import SimpleNamespace
from unittest.mock import patch

from gtm_agent.gtm_agent import (
    SYSTEM_PROMPT,
    data_service,
    gtm_agent,
    run_agent,
    send_prospect_email,
)


class SendProspectEmailTests(unittest.TestCase):
    def setUp(self):
        self.runtime = SimpleNamespace(config={"metadata": {"user_id": "REP-1"}})
        self.prospect = {
            "prospect_id": "LEAD-1",
            "name": "Taylor Example",
            "email": "taylor@example.com",
        }

    def call_email_tool(self, prospect=None):
        return send_prospect_email.func(
            prospect or self.prospect,
            "Hello",
            "Checking in",
            self.runtime,
            {"name": "Rep Example", "email": "rep@example.com"},
        )

    @patch.object(data_service, "get_prospect_record", return_value={"disqualified": True})
    @patch("gtm_agent.gtm_agent.uuid.uuid4")
    def test_disqualified_prospect_is_blocked(self, uuid4, get_prospect_record):
        result = self.call_email_tool()

        self.assertEqual(
            result,
            {
                "status": "blocked",
                "error": "Prospect is disqualified; email not sent.",
                "to": "taylor@example.com",
            },
        )
        get_prospect_record.assert_called_once_with("LEAD-1")
        uuid4.assert_not_called()

    @patch.object(data_service, "get_prospect_record", return_value={"disqualified": False})
    @patch("gtm_agent.gtm_agent.uuid.uuid4", return_value=SimpleNamespace(hex="1234567890abcd"))
    def test_qualified_prospect_is_sent(self, uuid4, get_prospect_record):
        result = self.call_email_tool()

        self.assertEqual(
            result,
            {
                "status": "sent",
                "message_id": "msg-1234567890ab",
                "to": "taylor@example.com",
                "to_name": "Taylor Example",
                "from": "rep@example.com",
                "from_name": "Rep Example",
                "subject": "Hello",
                "body": "Checking in",
            },
        )
        get_prospect_record.assert_called_once_with("LEAD-1")
        uuid4.assert_called_once()

    @patch.object(data_service, "get_prospect_record", return_value=None)
    def test_missing_record_does_not_block(self, get_prospect_record):
        result = self.call_email_tool()

        self.assertEqual(result["status"], "sent")
        get_prospect_record.assert_called_once_with("LEAD-1")

    @patch.object(data_service, "get_prospect_record")
    def test_missing_prospect_id_does_not_check_or_block(self, get_prospect_record):
        result = self.call_email_tool({"email": "taylor@example.com"})

        self.assertEqual(result["status"], "sent")
        get_prospect_record.assert_not_called()


class DisqualifiedLeadAgentTests(unittest.TestCase):
    def test_run_agent_returns_disqualification_reply_after_blocked_tool_call(self):
        self.assertIn("check the record with get_prospect", SYSTEM_PROMPT)
        self.assertIn("no email was sent", SYSTEM_PROMPT)
        messages = []

        def invoke(state, config):
            result = send_prospect_email.func(
                {
                    "prospect_id": "LEAD-1",
                    "name": "Taylor Example",
                    "email": "taylor@example.com",
                },
                "Hello",
                "Checking in",
                SimpleNamespace(config=config),
                {"name": "Rep Example", "email": "rep@example.com"},
            )
            messages.append(result)
            reply = "The lead is disqualified; no email was sent."
            return {"messages": [SimpleNamespace(content=reply)]}

        with patch.object(gtm_agent, "invoke", side_effect=invoke), patch.object(
            data_service, "get_prospect_record", return_value={"disqualified": True}
        ):
            result = run_agent("Email Taylor", user_id="REP-1")

        self.assertIn("disqualified", result["reply"])
        self.assertIn("no email was sent", result["reply"])
        self.assertEqual(messages[0]["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
