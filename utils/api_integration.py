import os
import requests
from dotenv import load_dotenv
import logging
import json
import re
from typing import List, Dict, Any
from telegram import Update
from telegram.ext import ContextTypes

load_dotenv()
logger = logging.getLogger(__name__)

PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")

class APIError(Exception):
    """Custom exception for API-related errors."""
    pass

def categorize_transaction(text: str) -> tuple:
    """
    Uses the Perplexity API to categorize a transaction and extract the amount.
    """
    url = "https://api.perplexity.ai/chat/completions"
    
    prompt = f"""
    Analyze the following transaction and provide:
    1. A general category (e.g., 'groceries', 'utilities', 'entertainment')
    2. A specific subcategory if applicable
    3. The amount spent
    4. The currency used

    Transaction: {text}

    Respond in JSON format:
    {{
        "category": "general_category",
        "subcategory": "specific_subcategory",
        "amount": float_value,
        "currency": "currency_code"
    }}
    """

    payload = {
        "model": "llama-3.1-sonar-small-128k-online",
        "messages": [
            {"role": "system", "content": "You are a financial categorization assistant."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1
    }
    headers = {
        "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        result = response.json()
        content = result['choices'][0]['message']['content']
        
        logger.debug(f"API response content: {content}")
        
        # Entferne mögliche Markdown-Formatierung
        content = re.sub(r'```json\n|\n```', '', content)
        
        # Try to parse the response as JSON
        try:
            parsed_content = json.loads(content)
            category = parsed_content['category']
            subcategory = parsed_content.get('subcategory', '')
            amount = float(parsed_content['amount'])
            currency = parsed_content['currency']
        except json.JSONDecodeError:
            # If JSON parsing fails, try to extract information using regex
            category_match = re.search(r'"category":\s*"(.+?)"', content)
            subcategory_match = re.search(r'"subcategory":\s*"(.+?)"', content)
            amount_match = re.search(r'"amount":\s*([\d.]+)', content)
            currency_match = re.search(r'"currency":\s*"(\w+)"', content)
            
            if category_match and amount_match:
                category = category_match.group(1)
                subcategory = subcategory_match.group(1) if subcategory_match else ''
                amount = float(amount_match.group(1))
                currency = currency_match.group(1) if currency_match else 'EUR'
            else:
                raise ValueError(f"Could not extract required information from API response: {content}")

        return category, subcategory, amount, currency

    except requests.RequestException as e:
        logger.error(f"API request failed: {e}")
        raise APIError("Failed to connect to the categorization service. Please try again later.")
    except Exception as e:
        logger.error(f"Unexpected error in categorize_transaction: {e}")
        raise APIError(f"An unexpected error occurred: {str(e)}. Please try again later.")

def get_financial_recommendations(user_id: int, transactions: List[Dict[str, Any]], budgets: List[Dict[str, Any]], goals: List[Dict[str, Any]]) -> str:
    """Generates financial recommendations based on user data."""
    context = create_financial_context(transactions, budgets, goals)
    
    url = "https://api.perplexity.ai/chat/completions"
    payload = {
        "model": "llama-3.1-sonar-small-128k-online",
        "messages": [
            {"role": "system", "content": "You are a financial advisor. Provide personalized advice based on the user's financial data."},
            {"role": "user", "content": f"Based on this financial data, provide 3 specific recommendations:\n\n{context}"}
        ],
        "temperature": 0.7,
        "max_tokens": 500
    }
    headers = {
        "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        result = response.json()
        return result['choices'][0]['message']['content']
    except requests.RequestException as e:
        logger.error(f"Failed to get recommendations: {e}")
        raise APIError("Failed to generate recommendations. Please try again later.")

def create_financial_context(transactions: List[Dict[str, Any]], budgets: List[Dict[str, Any]], goals: List[Dict[str, Any]]) -> str:
    """Creates a financial context string from user data."""
    context = "Financial Overview:\n\n"

    # Transaction analysis
    total_income = sum(t['amount'] for t in transactions if t['type'] == 'income')
    total_expenses = sum(t['amount'] for t in transactions if t['type'] == 'expense')
    top_expense_categories = get_top_categories(transactions, 'expense', 5)
    top_income_categories = get_top_categories(transactions, 'income', 3)

    context += f"Total Income: {total_income}€\n"
    context += f"Total Expenses: {total_expenses}€\n"
    context += f"Net Balance: {total_income - total_expenses}€\n\n"
    context += "Top 5 Expense Categories:\n" + "\n".join([f"- {cat}: {amount}€" for cat, amount in top_expense_categories])
    context += "\n\nTop 3 Income Sources:\n" + "\n".join([f"- {cat}: {amount}€" for cat, amount in top_income_categories])

    # Budget analysis
    context += "\n\nBudgets:\n"
    for budget in budgets:
        actual_spend = sum(t['amount'] for t in transactions if t['category'] == budget['name'] and t['type'] == 'expense')
        percentage = (actual_spend / budget['limit']) * 100 if budget['limit'] > 0 else 0
        context += f"- {budget['name']}: {actual_spend}€ of {budget['limit']}€ ({percentage:.1f}%)\n"

    # Goal analysis
    context += "\nFinancial Goals:\n"
    for goal in goals:
        progress = (goal['current_amount'] / goal['target_amount']) * 100 if goal['target_amount'] > 0 else 0
        context += f"- {goal['name']}: {goal['current_amount']}€ of {goal['target_amount']}€ ({progress:.1f}%)\n"

    return context

def get_top_categories(transactions: List[Dict[str, Any]], transaction_type: str, limit: int) -> List[tuple]:
    """Gets the top categories for income or expenses."""
    category_totals = {}
    for t in transactions:
        if t['type'] == transaction_type:
            category_totals[t['category']] = category_totals.get(t['category'], 0) + t['amount']
    return sorted(category_totals.items(), key=lambda x: x[1], reverse=True)[:limit]

async def debug_api_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Debug function to check raw API response."""
    user_input = "Test transaction 50€ for groceries"
    url = "https://api.perplexity.ai/chat/completions"
    
    prompt = f"""
    Analyze the following transaction and provide:
    1. A general category (e.g., 'groceries', 'utilities', 'entertainment')
    2. A specific subcategory if applicable
    3. The amount spent
    4. The currency used

    Transaction: {user_input}

    Respond in JSON format:
    {{
        "category": "general_category",
        "subcategory": "specific_subcategory",
        "amount": float_value,
        "currency": "currency_code"
    }}
    """

    payload = {
        "model": "llama-3.1-sonar-small-128k-online",
        "messages": [
            {"role": "system", "content": "You are a financial categorization assistant."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1
    }
    headers = {
        "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        result = response.json()
        content = result['choices'][0]['message']['content']
        await update.message.reply_text(f"Raw API response:\n\n{content}")
    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")