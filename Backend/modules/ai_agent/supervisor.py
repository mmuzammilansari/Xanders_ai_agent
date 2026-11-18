"""Supervisor: a manager agent that sends each question to the right worker agent."""
from langgraph.prebuilt import create_react_agent
from langgraph_supervisor import create_supervisor
from modules.ai_agent.graph import create_chat_model
from modules.ai_agent.tools import fetch_menu, validate_order_id, log_complaint, get_discounts, place_order



def build_supervisor(llm="groq"):
    model = create_chat_model(llm)

    menu_agent = create_react_agent(
        model=model,
        tools=[fetch_menu],
        name="menu_agent",
        prompt="You answer menu and price questions. Prices are in PKR. Always use fetch_menu. Write prices like Rs. 850, never use the peso sign.",
    )
    complaint_agent = create_react_agent(
        model=model,
        tools=[validate_order_id, log_complaint],
        name="complaint_agent",
        prompt=("You handle complaints. Collect customer name, phone, order ID and complaint. "
                "Check the order ID with validate_order_id, then save with log_complaint. "
                "Ask for missing details. Never invent a complaint ID."),
    )
    order_agent = create_react_agent(
        model=model,
        tools=[place_order],
        name="order_agent",
        prompt=("You handle customer orders. Collect the customer's name, phone number, "
                "and requested items with quantities before placing an order. "
                "Ask for any missing details and never claim an order was placed before the tool succeeds."),
    )
    offer_agent = create_react_agent(
        model=model,
        tools=[get_discounts],
        name="offer_agent",
        prompt="Answer questions about current discounts using get_discounts.",
    )
    supervisor = create_supervisor(
        agents=[menu_agent, complaint_agent, offer_agent, order_agent],
        model=model,
        prompt=("You are the manager of Xander Restaurant support. "
                "Menu or price questions -> menu_agent. Complaints -> complaint_agent. "
                "Offer or discount questions -> offer_agent. New orders -> order_agent. "
                "For greetings, answer yourself in one short line. "
                "After a worker agent answers, write nothing more: repeat the worker's answer exactly."),
    )
    return supervisor.compile()





