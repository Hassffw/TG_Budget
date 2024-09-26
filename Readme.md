# Personal Budget Telegram app with Perplexity API

This Telegram bot helps users manage their personal finances by tracking expenses, setting budgets, and providing financial advice.

## Features

- Track expenses and income
- Set and monitor budgets
- Set financial goals
- Generate financial reports
- Get personalized financial advice
- Weekly and monthly summaries

## Setup

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/personal-budget-bot.git
   cd personal-budget-bot
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Set up environment variables:
   Create a `.env` file in the root directory and add the following:
   ```
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   PERPLEXITY_API_KEY=your_perplexity_api_key
   ```

4. Initialize the database:
   ```
   python initialize_db.py
   ```

5. Run the bot:
   ```
   python telegram_budget_app.py
   ```

## Usage

Start a chat with the bot on Telegram and use the following commands:

- `/start` - Start the bot and create an account
- `/help` - Show available commands
- `/addexpense` - Add an expense
- `/addincome` - Add an income
- `/setbudget` - Set a budget for a category
- `/viewbudget` - View current budgets
- `/setgoal` - Set a financial goal
- `/viewgoals` - View current financial goals
- `/report` - Generate a financial report
- `/advice` - Get personalized financial advice
- `/list` - List recent transactions
- `/delete` - Delete a transaction
- `/mergecategories` - Merge two categories

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License.
