"""LLM engine with a scripted fake model: tool calling, confirmation, guards and fallback."""
from dataclasses import replace

import pytest

from app.ai import llm_client
from app.ai.llm_client import LLMReply, LLMUnavailable, ToolCall, parse_model_output
from app.core.config import settings
from app.models import AvaAppointment, AvaHandoffRequest, AvaLead
from app.services import chat_service

from .conftest import TUESDAY


class FakeLLM:
    """Returns scripted replies in order and records every prompt it receives."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def is_ready(self):
        return True

    def complete(self, messages, tools):
        self.calls.append({"messages": [dict(m) for m in messages], "tools": tools})
        if not self.replies:
            raise AssertionError("FakeLLM called more often than scripted")
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def text(content):
    return LLMReply(content=content)


def tool(tool_name, **arguments):
    return LLMReply(content=None, tool_calls=[ToolCall(id="c1", name=tool_name, arguments=arguments)])


@pytest.fixture()
def fake(client, monkeypatch):
    # These tests exercise the LLM path itself, so every message goes to the LLM.
    monkeypatch.setattr(chat_service, "settings", replace(settings, llm_mode="always"))
    holder = {}

    def use(*replies):
        holder["llm"] = FakeLLM(*replies)
        llm_client.set_llm_client(holder["llm"])
        return holder["llm"]

    yield use
    llm_client.set_llm_client(None)


def say(client, message, session_id=None, **extra):
    res = client.post("/api/chat", json={"message": message, "session_id": session_id, **extra})
    assert res.status_code == 200, res.text
    return res.json()


def test_plain_answer_and_prompt_contains_verified_facts(client, fake):
    llm = fake(text("Hi! I'm Ava. How can I help?"))
    r = say(client, "hello")
    assert r["engine"] == "llm" and r["reply"] == "Hi! I'm Ava. How can I help?"
    system = llm.calls[0]["messages"][0]["content"]
    assert "WebeXcellence" in system and "Website Design" in system and "Sun closed" in system
    assert len(llm.calls[0]["tools"]) == 10


def test_history_is_sent_on_next_turn(client, fake):
    llm = fake(text("Hello!"), text("Sure."))
    sid = say(client, "hello")["session_id"]
    say(client, "and services?", sid)
    roles = [m["role"] for m in llm.calls[1]["messages"]]
    assert roles == ["system", "user", "assistant", "user"]


def test_info_tool_result_is_fed_back(client, fake):
    llm = fake(tool("search_faq", query="refund"), text("Refund terms are agreed per contract."))
    r = say(client, "do you refund?")
    assert r["reply"].startswith("Refund terms")
    tool_message = llm.calls[1]["messages"][-1]
    assert tool_message["role"] == "tool" and "refund" in tool_message["content"].lower()


def test_booking_needs_confirmation_and_is_executed_by_backend(client, db, fake):
    llm = fake(tool("book_appointment", name="Rahul Verma", phone="9876501234", service="Website Design",
                    date=TUESDAY.isoformat(), time="10:00"))
    r = say(client, "Book me Tuesday 10am, Rahul Verma, 9876501234, website design")
    assert "Reply yes to confirm" in r["reply"]
    assert db.query(AvaAppointment).count() == 0

    r = say(client, "yes", r["session_id"])  # no LLM call needed for the confirmation
    assert len(llm.calls) == 1
    assert "Booking code: AVA-" in r["reply"]
    appointment = db.query(AvaAppointment).one()
    assert appointment.booking_code in r["reply"] and appointment.source == "website_chat"


def test_booking_declined(client, db, fake):
    fake(tool("book_appointment", name="Rahul Verma", phone="9876501234", service="Website Design",
              date=TUESDAY.isoformat(), time="10:00"))
    sid = say(client, "book it")["session_id"]
    assert "nothing has been changed" in say(client, "no", sid)["reply"]
    assert db.query(AvaAppointment).count() == 0


def test_booking_with_missing_fields_asks_for_them(client, db, fake):
    fake(tool("book_appointment", name="Rahul Verma", service="Website Design", date=TUESDAY.isoformat()))
    r = say(client, "book")
    assert "your phone number" in r["reply"] and "the time" in r["reply"]
    assert db.query(AvaAppointment).count() == 0


def test_booking_taken_slot_offers_other_times(client, db, fake):
    client.post("/api/appointments", json={"name": "Anita Rao", "phone": "9876500000", "service": "Website Design",
                                           "appointment_date": TUESDAY.isoformat(), "start_time": "10:00"})
    fake(tool("book_appointment", name="Rahul Verma", phone="9876501234", service="Website Design",
              date=TUESDAY.isoformat(), time="10:00"))
    r = say(client, "book tuesday 10")
    assert r["ui_action"] == "select_time" and "already booked" in r["reply"]


def test_slot_taken_between_proposal_and_confirmation(client, db, fake):
    fake(tool("book_appointment", name="Rahul Verma", phone="9876501234", service="Website Design",
              date=TUESDAY.isoformat(), time="10:00"))
    sid = say(client, "book")["session_id"]
    client.post("/api/appointments", json={"name": "Anita Rao", "phone": "9876500000", "service": "Website Design",
                                           "appointment_date": TUESDAY.isoformat(), "start_time": "10:00"})
    r = say(client, "yes", sid)
    assert r["ui_action"] == "select_time"
    assert db.query(AvaAppointment).count() == 1  # only the other customer's booking


def test_check_availability_shows_pickers(client, fake):
    fake(tool("check_availability"))
    r = say(client, "when are you free?")
    assert r["ui_action"] == "select_date" and r["data"]["dates"]
    fake(tool("check_availability", date=TUESDAY.isoformat()))
    r = say(client, "and on tuesday?", r["session_id"])
    assert r["ui_action"] == "select_time" and r["data"]["slots"][0]["time"] == "09:00"


def test_date_picker_click_is_handled_without_llm(client, fake):
    llm = fake()
    r = say(client, "", action="select_date", selected_date=TUESDAY.isoformat())
    assert r["ui_action"] == "select_time" and llm.calls == []


def test_time_picker_click_goes_to_llm_as_text(client, fake):
    llm = fake(text("Great, may I have your full name?"))
    say(client, "", action="select_time", selected_date=TUESDAY.isoformat(), selected_time="11:00")
    assert f"{TUESDAY.isoformat()} at 11:00" in llm.calls[0]["messages"][-1]["content"]


def test_reschedule_and_cancel_check_ownership(client, db, fake):
    res = client.post("/api/appointments", json={"name": "Anita Rao", "phone": "9876500000",
                                                 "service": "Website Design",
                                                 "appointment_date": TUESDAY.isoformat(), "start_time": "10:00"})
    code = res.json()["appointment"]["booking_code"]

    fake(tool("cancel_appointment", booking_code=code, phone="9999999999"))
    assert "could not find" in say(client, "cancel it")["reply"]

    fake(tool("reschedule_appointment", booking_code=code, phone="9876500000", new_date=TUESDAY.isoformat(),
              new_time="13:00"))
    r = say(client, "move it to 1pm")
    assert "Reply yes to confirm" in r["reply"]
    assert "now on" in say(client, "yes", r["session_id"])["reply"]
    assert db.query(AvaAppointment).one().appointment_date.hour == 13

    fake(tool("cancel_appointment", booking_code=code, phone="9876500000"))
    r = say(client, "cancel please")
    assert "cancelled" in say(client, "yes", r["session_id"])["reply"]
    assert db.query(AvaAppointment).one().status == "cancelled"


def test_lead_and_handoff_tools(client, db, fake):
    fake(tool("create_customer_lead", name="Karan Mehta", phone="9876522222", service="E-commerce Development"))
    assert "saved your details" in say(client, "call me about a shop")["reply"]
    assert db.query(AvaLead).one().phone == "9876522222"

    fake(tool("request_human_handoff", reason="Wants to discuss a contract"))
    r = say(client, "I need a person")
    assert "Nobody has replied yet" in r["reply"]
    assert db.query(AvaHandoffRequest).one().reason == "Wants to discuss a contract"


def test_invalid_lead_reports_problem(client, db, fake):
    fake(tool("create_customer_lead", name="Karan Mehta"))
    assert "phone number or an e-mail" in say(client, "contact me")["reply"]
    assert db.query(AvaLead).count() == 0


def test_guard_blocks_false_booking_claim(client, db, fake):
    fake(text("Great news, your appointment is booked for Tuesday!"))
    r = say(client, "book me")
    assert "haven't booked" in r["reply"]
    assert db.query(AvaAppointment).count() == 0


def test_guard_blocks_invented_booking_code(client, fake):
    fake(text("Your code is AVA-QQQQQQ, see you then."))
    assert "made a mistake" in say(client, "what's my code")["reply"]


def test_llm_failure_falls_back_to_rules(client, fake):
    fake(LLMUnavailable("timeout"))
    r = say(client, "hello")
    assert r["engine"] == "rules" and "WebeXcellence" in r["reply"]


def test_empty_llm_reply_falls_back(client, fake):
    fake(text("   "))
    assert say(client, "hello")["engine"] == "rules"


def test_too_many_tool_rounds_falls_back(client, fake):
    fake(*[tool("get_services") for _ in range(10)])
    assert say(client, "services?")["engine"] == "rules"


def test_unknown_and_invalid_tools_are_reported_to_model(client, fake):
    llm = fake(
        LLMReply(content=None, tool_calls=[ToolCall(id="1", name="drop_database", arguments={})]),
        LLMReply(content=None, tool_calls=[ToolCall(id="2", name="__invalid__", arguments={})]),
        text("Sorry, how can I help?"),
    )
    assert say(client, "hi")["reply"] == "Sorry, how can I help?"
    assert "Unknown tool" in llm.calls[1]["messages"][-1]["content"]


def test_model_not_ready_uses_rules(client):
    class NotReady(FakeLLM):
        def is_ready(self):
            return False

    llm_client.set_llm_client(NotReady())
    assert say(client, "hello")["engine"] == "rules"


def test_parse_qwen_tool_call_format():
    out = parse_model_output('Sure.<tool_call>\n{"name": "get_services", "arguments": {}}\n</tool_call>')
    assert out.content == "Sure." and out.tool_calls[0].name == "get_services"
    out = parse_model_output('<tool_call>{"name": "search_faq", "arguments": "{\\"query\\": \\"x\\"}"}</tool_call>')
    assert out.tool_calls[0].arguments == {"query": "x"}
    out = parse_model_output("<tool_call>{not json}</tool_call>")
    assert out.tool_calls[0].name == "__invalid__"
    assert parse_model_output("Just text").tool_calls == []


# --- hybrid routing ----------------------------------------------------------------


def test_hybrid_answers_clear_messages_without_llm(client):
    llm = FakeLLM(text("unused"))
    llm_client.set_llm_client(llm)
    r = say(client, "what are your opening hours")
    assert r["engine"] == "rules" and llm.calls == []


def test_hybrid_sends_unclear_or_detailed_messages_to_llm(client):
    llm = FakeLLM(text("Let me help."), text("Noted."))
    llm_client.set_llm_client(llm)
    assert say(client, "blorp fizzle wobble")["engine"] == "llm"  # unknown intent
    detailed = "My name is Rahul Verma, phone 9876501234, I want website design on Wednesday at 10 in the morning"
    assert say(client, detailed)["engine"] == "llm"  # many details in one message
    assert len(llm.calls) == 2


def test_hybrid_keeps_llm_when_it_asked_a_question(client):
    llm = FakeLLM(text("Sure! What is your full name?"), text("Thanks Rahul, and your phone number?"))
    llm_client.set_llm_client(llm)
    sid = say(client, "zzz unclear request about stuff")["session_id"]
    assert say(client, "hello", sid)["engine"] == "llm"  # continues the LLM's question
