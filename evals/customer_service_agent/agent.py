import logging
import os
from typing import Dict, List, Any
from google.adk.agents import Agent

import copy
# Mock data stored in memory for the session
DEFAULT_MOCK_DATA = {
    "CUST001": {
        "orders": [
            {"order_id": "ORD-101", "date": "2023-10-15", "items": ["Wireless Headphones"], "total": 120.00, "status": "delivered"},
            {"order_id": "ORD-102", "date": "2023-11-01", "items": ["USB-C Cable", "Phone Case"], "total": 35.00, "status": "shipped"}
        ]
    },
    "CUST002": {
        "orders": [
            {"order_id": "ORD-201", "date": "2023-09-20", "items": ["Smart Watch"], "total": 250.00, "status": "delivered"}
        ]
    }
}

MOCK_DATA = copy.deepcopy(DEFAULT_MOCK_DATA)

def reset_mock_data():
    global MOCK_DATA
    MOCK_DATA = copy.deepcopy(DEFAULT_MOCK_DATA)

def get_purchase_history(customer_id: str) -> Dict[str, Any]:
    """
    Retrieves the purchase history for a given customer, including order status.

    Args:
        customer_id: The unique identifier for the customer.

    Returns:
        A dictionary containing a list of past orders with their current status.
    """
    return MOCK_DATA.get(customer_id, {"orders": [], "message": "No purchase history found for this customer."})

def issue_refund(order_id: str, reason: str) -> Dict[str, Any]:
    """
    Issues a refund for a specific order and updates its status.

    Args:
        order_id: The unique identifier for the order.
        reason: The reason for the refund.

    Returns:
        A dictionary confirming the refund status and updated order information.
    """
    for customer_id, data in MOCK_DATA.items():
        for order in data["orders"]:
            if order["order_id"] == order_id:
                if order["status"] == "refunded":
                    return {
                        "status": "error",
                        "message": f"Order {order_id} has already been refunded."
                    }
                order["status"] = "refunded"
                return {
                    "status": "success",
                    "order_id": order_id,
                    "new_status": "refunded",
                    "refund_amount": f"Full refund of ${order['total']} processed",
                    "message": f"Refund issued for order {order_id} due to: {reason}"
                }

    return {
        "status": "error",
        "message": f"Order ID {order_id} not found or not eligible for refund."
    }

def lookup_product_info(product_name: str) -> Dict[str, Any]:
    """
    Looks up details for a specific product.

    Args:
        product_name: The name of the product to look up.

    Returns:
        A dictionary with product details.
    """
    # Mock data
    products = {
        "wireless headphones": {
            "price": 120.00,
            "in_stock": True,
            "description": "Noise-canceling wireless headphones with 20-hour battery life."
        },
        "smart watch": {
            "price": 250.00,
            "in_stock": False,
            "description": "Advanced fitness tracking and notifications."
        },
        "usb-c cable": {
            "price": 15.00,
            "in_stock": True,
            "description": "6ft braided USB-C to USB-C cable."
        }
    }

    normalized_name = product_name.lower()
    if normalized_name in products:
        return products[normalized_name]
    else:
        return {"message": "Product not found."}

agent_instruction = """
You are a helpful and efficient retail customer service representative for Cymbal Home & Garden.
Your goal is to assist customers with their purchase history, refunds, and product inquiries.

**Guidelines:**
1.  **Identify the Customer:** If a customer asks about their history or order status, ask for their Customer ID if they haven't provided it.
2.  **Check Order Status:** Use `get_purchase_history` to see the current status of orders (e.g., ordered, shipped, delivered, refunded).
3.  **Handle Refunds:** When a customer wants a refund, ask for the Order ID and the reason for the refund. Use the `issue_refund` tool. If the customer mentions damage, use "damaged" as the reason.
4.  **Product Inquiries:** For product questions, use `lookup_product_info`. If a product is out of stock, inform the customer.
5.  **Be Polite & Professional:** Always use a friendly, professional tone.
6.  **Prioritize Solutions:** Try to resolve the customer's issue quickly using the available tools.

**Available Tools:**
* `get_purchase_history`: Get past orders and their current status for a customer.
* `issue_refund`: Process a refund for an order and update its status.
* `lookup_product_info`: Get details about a product.
"""

agent = Agent(
    model="gemini-3.5-flash",
    name="customer_service_agent",
    instruction=agent_instruction,
    tools=[
        get_purchase_history,
        issue_refund,
        lookup_product_info,
    ],
)

root_agent = agent
