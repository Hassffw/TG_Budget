import logging
import os
from dotenv import load_dotenv
from telegram import Update, ForceReply, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    ConversationHandler,
    CallbackQueryHandler,
)
from sqlalchemy.orm import sessionmaker
from sqlalchemy import func
from database import engine, SessionLocal
from database.models import User, Transaction, Budget, Goal
from datetime import datetime, time, timedelta
from utils.api_integration import categorize_transaction, get_financial_recommendations, APIError, debug_api_response
from utils.visualization import generate_financial_report
from utils.reminders import schedule_budget_check_job
import bcrypt
import pytz
import calendar

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize database session
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Define states for Conversation Handlers
ADD_TRANSACTION, SET_BUDGET, SET_GOAL = range(3)

# Fügen Sie diese Funktion am Anfang der Datei hinzu
def normalize_category(category: str) -> str:
    """Normalizes category names to merge similar categories."""
    category = category.lower()
    
    category_mappings = {
        'netflix': 'streaming_subscription',
        'disney+': 'streaming_subscription',
        'disney plus': 'streaming_subscription',
        'amazon prime': 'streaming_subscription',
        'hulu': 'streaming_subscription',
        'spotify': 'music_subscription',
        'apple music': 'music_subscription',
        'youtube premium': 'streaming_subscription',
        'hbo': 'streaming_subscription',
        'subscription': 'subscription',
        'streaming': 'streaming_subscription',
        'mobilfunk': 'telecommunication',
        'handy': 'telecommunication',
        'telefon': 'telecommunication',
        'internet': 'telecommunication',
        'lebensmittel': 'groceries',
        'supermarkt': 'groceries',
        'restaurant': 'dining_out',
        'essen gehen': 'dining_out',
        'strom': 'utilities',
        'gas': 'utilities',
        'heizung': 'utilities',
        'wasser': 'utilities',
        'gehalt': 'income',
        'lohn': 'income',
        'bonus': 'income',
        'miete': 'housing',
        'nebenkosten': 'housing',
        'versicherung': 'insurance',
        'auto': 'transportation',
        'bahn': 'transportation',
        'bus': 'transportation',
        'taxi': 'transportation',
        'kleidung': 'shopping',
        'schuhe': 'shopping',
        'elektronik': 'shopping',
    }
    
    for key, value in category_mappings.items():
        if key in category:
            return value
    
    return category

async def merge_categories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Erlaubt Benutzern, Kategorien manuell zusammenzuführen."""
    user = update.effective_user
    session = SessionLocal()
    db_user = session.query(User).filter(User.telegram_id == user.id).first()

    if not context.args or len(context.args) != 2:
        await update.message.reply_text("Bitte gib zwei Kategorien an, die du zusammenführen möchtest. Beispiel: /mergecategories Kategorie1 Kategorie2")
        session.close()
        return

    old_category, new_category = context.args

    try:
        # Aktualisiere alle Transaktionen mit der alten Kategorie
        transactions = session.query(Transaction).filter(
            Transaction.user_id == db_user.id,
            Transaction.category == old_category
        ).all()

        for transaction in transactions:
            transaction.category = new_category

        # Aktualisiere das Budget, falls vorhanden
        budget = session.query(Budget).filter(
            Budget.user_id == db_user.id,
            Budget.name == old_category
        ).first()

        if budget:
            existing_new_budget = session.query(Budget).filter(
                Budget.user_id == db_user.id,
                Budget.name == new_category
            ).first()

            if existing_new_budget:
                existing_new_budget.limit += budget.limit
                session.delete(budget)
            else:
                budget.name = new_category

        session.commit()
        await update.message.reply_text(f"Kategorien '{old_category}' und '{new_category}' wurden erfolgreich zusammengeführt.")
    except Exception as e:
        logger.error(f"Fehler beim Zusammenführen der Kategorien: {e}")
        await update.message.reply_text("Es gab einen Fehler beim Zusammenführen der Kategorien.")
    finally:
        session.close()

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sendet eine übersichtliche Hilfemeldung mit allen verfügbaren Befehlen."""
    help_text = (
        "🤖 Budget-Bot Befehle:\n\n"
        "📊 Finanzen verwalten:\n"
        "/addexpense - Ausgabe hinzufügen\n"
        "/addincome - Einnahme hinzufügen\n"
        "/list - Letzte Transaktionen anzeigen\n"
        "/delete <nummer> - Transaktion löschen\n\n"
        "💰 Budgets & Ziele:\n"
        "/setbudget - Budget festlegen\n"
        "/viewbudget - Budgets anzeigen\n"
        "/setgoal - Finanzziel setzen\n"
        "/viewgoals - Ziele anzeigen\n\n"
        "📈 Berichte & Analysen:\n"
        "/report - Finanzübersicht generieren\n"
        "/advice - Finanzratschläge erhalten\n\n"
        "🛠 Sonstiges:\n"
        "/mergecategories <alt> <neu> - Kategorien zusammenführen\n"
        "/help - Diese Hilfe anzeigen\n\n"
        "Tippe einen Befehl oder /help <befehl> für mehr Infos."
    )
    await update.message.reply_text(help_text)

async def detailed_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gibt detaillierte Hilfe zu einem bestimmten Befehl."""
    if not context.args:
        await help_command(update, context)
        return

    command = context.args[0].lower()
    help_texts = {
        "addexpense": "Füge eine neue Ausgabe hinzu. Beispiel: /addexpense 50€ für Lebensmittel",
        "addincome": "Füge eine neue Einnahme hinzu. Beispiel: /addincome 1000€ Gehalt",
        "list": "Zeigt deine letzten 10 Transaktionen an.",
        "delete": "Löscht eine Transaktion. Nutze /list und dann /delete <nummer>",
        "setbudget": "Lege ein neues Budget fest. Beispiel: /setbudget Lebensmittel: 300€ pro Monat",
        "viewbudget": "Zeigt alle deine aktuellen Budgets an.",
        "setgoal": "Setze ein finanzielles Ziel. Beispiel: /setgoal Urlaub: 1000€ bis 31.12.2023",
        "viewgoals": "Zeigt alle deine aktuellen finanziellen Ziele an.",
        "report": "Generiert einen visuellen Bericht deiner Ausgaben und Einnahmen.",
        "advice": "Gibt dir personalisierte Finanzratschläge basierend auf deinen Daten.",
        "mergecategories": "Führt zwei Kategorien zusammen. Beispiel: /mergecategories Essen Lebensmittel"
    }

    if command in help_texts:
        await update.message.reply_text(f"{command}:\n\n{help_texts[command]}")
    else:
        await update.message.reply_text("Unbekannter Befehl. Nutze /help für eine Übersicht aller Befehle.")

# ----- Handler-Funktionen -----

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Begrüßungsnachricht und Registrierung des Benutzers."""
    user = update.effective_user
    session = SessionLocal()
    db_user = session.query(User).filter(User.telegram_id == user.id).first()
    if not db_user:
        # Sichere Passwort-Hashing
        plain_password = "IhrStandardPasswort"  # Ersetzen Sie dies durch ein tatsächliches Passwort
        hashed = bcrypt.hashpw(plain_password.encode('utf-8'), bcrypt.gensalt())
        
        db_user = User(
            telegram_id=user.id,
            username=user.username,
            hashed_password=hashed.decode('utf-8')  # Speichern Sie als String
        )
        session.add(db_user)
        session.commit()
        session.refresh(db_user)
        logger.info(f"Neuer Benutzer erstellt: Telegram ID = {db_user.telegram_id}, Username = {db_user.username}")
        await update.message.reply_text(
            f"Willkommen, {user.first_name}! Dein Konto wurde erstellt.",
            reply_markup=ForceReply(selective=True)
        )
    else:
        logger.info(f"Benutzer gefunden: Telegram ID = {db_user.telegram_id}, Username = {db_user.username}")
        await update.message.reply_text(
            f"Willkommen zurück, {user.first_name}!",
            reply_markup=ForceReply(selective=True)
        )
    session.close()

async def add_transaction_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the process of adding a transaction."""
    context.user_data['transaction_type'] = 'expense' if update.message.text == '/addexpense' else 'income'
    
    keyboard = [
        [InlineKeyboardButton("Cancel", callback_data='cancel')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"Please enter the details of the {'expense' if context.user_data['transaction_type'] == 'expense' else 'income'}. For example:\n"
        f"{'50€ for groceries' if context.user_data['transaction_type'] == 'expense' else '1000€ salary'}",
        reply_markup=reply_markup
    )
    return ADD_TRANSACTION

async def add_transaction_end(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Processes the added transaction."""
    user_input = update.message.text
    user = update.effective_user
    session = SessionLocal()

    try:
        # Verwende die verbesserte Kategorisierungsfunktion
        category, subcategory, amount, currency = categorize_transaction(user_input)

        if amount <= 0:
            await update.message.reply_text("Der Betrag muss größer als 0 sein.")
            return ADD_TRANSACTION

        db_user = session.query(User).filter(User.telegram_id == user.id).first()
        if not db_user:
            await update.message.reply_text("Benutzerkonto nicht gefunden. Bitte starte den Bot mit /start.")
            return ConversationHandler.END

        transaction = Transaction(
            user_id=db_user.id,
            amount=amount,
            description=user_input,
            date=datetime.now(),
            category=category,
            subcategory=subcategory,
            currency=currency,
            type=context.user_data.get('transaction_type', 'expense')
        )
        session.add(transaction)
        session.commit()

        await update.message.reply_text(
            f"{'Ausgabe' if transaction.type == 'expense' else 'Einnahme'} hinzugefügt: "
            f"{transaction.amount} {transaction.currency} für {transaction.description}\n"
            f"Kategorie: {transaction.category}\n"
            f"Unterkategorie: {transaction.subcategory}"
        )

        if transaction.type == 'expense':
            await check_budget(update, context, db_user, transaction.category, transaction.amount)

    except Exception as e:
        logger.error(f"Fehler beim Hinzufügen der Transaktion: {e}")
        await update.message.reply_text("Es gab einen Fehler beim Hinzufügen der Transaktion.")
    finally:
        session.close()

    return ConversationHandler.END

async def check_budget(update: Update, context: ContextTypes.DEFAULT_TYPE, db_user: User, category: str, amount: float) -> None:
    """Checks the budget for a given category and sends warnings if necessary."""
    session = SessionLocal()
    try:
        budget = session.query(Budget).filter(Budget.user_id == db_user.id, Budget.name == category).first()
        if budget:
            total = session.query(func.sum(Transaction.amount)).filter(
                Transaction.user_id == db_user.id,
                Transaction.category == category,
                Transaction.type == 'expense'
            ).scalar() or 0.0

            if total > budget.limit:
                percentage = (total / budget.limit) * 100
                await update.message.reply_text(
                    f"⚠️ Warning: You've exceeded your budget for {category}!\n"
                    f"Limit: {budget.limit}€\n"
                    f"Current expenses: {total}€ ({percentage:.1f}% of budget)"
                )
            elif total > budget.limit * 0.8:
                percentage = (total / budget.limit) * 100
                await update.message.reply_text(
                    f"⚠️ Attention: You've used {percentage:.1f}% of your budget for {category}.\n"
                    f"Limit: {budget.limit}€\n"
                    f"Current expenses: {total}€"
                )
    finally:
        session.close()

async def set_budget_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Startet den Prozess zum Setzen eines Budgets."""
    await update.message.reply_text(
        "Bitte gib das Budget ein. Zum Beispiel:\n"
        "Lebensmittel: 300€ pro Monat"
    )
    return SET_BUDGET

async def set_budget_end(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Verarbeitet das gesetzte Budget."""
    user_input = update.message.text
    user = update.effective_user
    session = SessionLocal()

    try:
        # Beispielhafte einfache Parsing-Logik
        if ':' not in user_input:
            await update.message.reply_text("Ungültiges Format. Bitte verwende 'Kategorie: Betrag'.")
            session.close()
            return ConversationHandler.END

        category, amount_period = user_input.split(':', 1)
        amount, period = amount_period.strip().split('€ pro ')
        amount = float(amount)
        period = period.lower()

        db_user = session.query(User).filter(User.telegram_id == user.id).first()
        budget = session.query(Budget).filter(Budget.user_id == db_user.id, Budget.name == category.strip()).first()

        if not budget:
            budget = Budget(
                user_id=db_user.id,
                name=category.strip(),
                limit=amount
            )
            session.add(budget)
        else:
            budget.limit = amount

        session.commit()
        await update.message.reply_text(f"Budget für {budget.name} auf {budget.limit}€ pro {period} gesetzt.")
        session.close()
    except Exception as e:
        logger.error(f"Fehler beim Setzen des Budgets: {e}")
        await update.message.reply_text("Es gab einen Fehler beim Setzen des Budgets.")
        session.close()

    return ConversationHandler.END

async def set_goal_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Startet den Prozess zum Setzen eines finanziellen Ziels."""
    await update.message.reply_text(
        "Bitte gib dein finanzielles Ziel ein. Zum Beispiel:\n"
        "Sparen: 1000€ bis 31.12.2024"
    )
    return SET_GOAL

async def set_goal_end(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Verarbeitet das gesetzte finanzielle Ziel."""
    user_input = update.message.text
    user = update.effective_user
    session = SessionLocal()

    try:
        # Beispielhafte einfache Parsing-Logik
        if ':' not in user_input or 'bis' not in user_input:
            await update.message.reply_text("Ungültiges Format. Bitte verwende 'Beschreibung: Betrag bis Datum'.")
            session.close()
            return ConversationHandler.END

        description, rest = user_input.split(':', 1)
        amount, deadline_str = rest.strip().split(' bis ')
        amount = float(amount.replace('€', ''))
        deadline = datetime.strptime(deadline_str.strip(), '%d.%m.%Y')

        db_user = session.query(User).filter(User.telegram_id == user.id).first()
        goal = Goal(
            user_id=db_user.id,
            name=description.strip(),
            target_amount=amount,
            current_amount=0.0
        )
        session.add(goal)
        session.commit()
        await update.message.reply_text(f"Finanzielles Ziel gesetzt: {goal.name} - {goal.target_amount}€ bis {deadline.strftime('%d.%m.%Y')}.")
        session.close()
    except Exception as e:
        logger.error(f"Fehler beim Setzen des Ziels: {e}")
        await update.message.reply_text("Es gab einen Fehler beim Setzen des Ziels.")
        session.close()

    return ConversationHandler.END

async def view_budget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Zeigt die aktuellen Budgets des Benutzers."""
    user = update.effective_user
    session = SessionLocal()
    db_user = session.query(User).filter(User.telegram_id == user.id).first()
    budgets = session.query(Budget).filter(Budget.user_id == db_user.id).all()

    if not budgets:
        await update.message.reply_text("Du hast noch keine Budgets gesetzt.")
    else:
        budget_text = "Deine aktuellen Budgets:\n"
        for budget in budgets:
            budget_text += f"- {budget.name}: {budget.limit}€\n"
        await update.message.reply_text(budget_text)
    session.close()

async def view_goals(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Zeigt die aktuellen finanziellen Ziele des Benutzers."""
    user = update.effective_user
    session = SessionLocal()
    db_user = session.query(User).filter(User.telegram_id == user.id).first()
    goals = session.query(Goal).filter(Goal.user_id == db_user.id).all()

    if not goals:
        await update.message.reply_text("Du hast noch keine finanziellen Ziele gesetzt.")
    else:
        goal_text = "Deine aktuellen finanziellen Ziele:\n"
        for goal in goals:
            goal_text += f"- {goal.name}: {goal.target_amount}€\n"
        await update.message.reply_text(goal_text)
    session.close()

async def generate_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generiert und sendet einen Finanzberich an den Benutzer."""
    user = update.effective_user
    session = SessionLocal()
    db_user = session.query(User).filter(User.telegram_id == user.id).first()

    try:
        report_image = generate_financial_report(db_user.id)
        with open(report_image, 'rb') as photo:
            await update.message.reply_photo(photo=photo, caption="Dein Finanzbericht:")
        os.remove(report_image)  # Entferne das temporäre Bild
    except ValueError as ve:
        logger.error(f"Fehler beim Generieren des Berichts: {ve}")
        await update.message.reply_text(str(ve))
    except Exception as e:
        logger.error(f"Fehler beim Generieren des Berichts: {e}")
        await update.message.reply_text("Es gab einen Fehler beim Generieren des Berichts.")
    finally:
        session.close()

async def list_transactions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Listet die letzten Transaktionen des Benutzers auf."""
    user = update.effective_user
    session = SessionLocal()
    db_user = session.query(User).filter(User.telegram_id == user.id).first()
    
    transactions = session.query(Transaction).filter(Transaction.user_id == db_user.id).order_by(Transaction.date.desc()).limit(10).all()
    
    if not transactions:
        await update.message.reply_text("Du hast noch keine Transaktionen.")
    else:
        message = "Deine letzten Transaktionen:\n\n"
        for i, tx in enumerate(transactions, 1):
            message += f"{i}. {tx.date.strftime('%d.%m.%Y')} - {tx.amount}€ für {tx.category} ({tx.type})\n"
        
        await update.message.reply_text(message)
    
    session.close()

async def delete_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Löscht eine Transaktion basierend auf der Nummer aus der Liste."""
    user = update.effective_user
    session = SessionLocal()
    db_user = session.query(User).filter(User.telegram_id == user.id).first()
    
    if not context.args:
        await update.message.reply_text("Bitte gib die Nummer der Transaktion an, die du löschen möchtest.")
        session.close()
        return
    
    try:
        index = int(context.args[0]) - 1
        transaction = session.query(Transaction).filter(Transaction.user_id == db_user.id).order_by(Transaction.date.desc()).offset(index).first()
        
        if transaction:
            session.delete(transaction)
            session.commit()
            await update.message.reply_text(f"Transaktion gelöscht: {transaction.amount}€ für {transaction.category}")
        else:
            await update.message.reply_text("Transaktion nicht gefunden.")
    except ValueError:
        await update.message.reply_text("Bitte gib eine gültige Nummer ein.")
    except Exception as e:
        logger.error(f"Fehler beim Löschen der Transaktion: {e}")
        await update.message.reply_text("Es gab einen Fehler beim Löschen der Transaktion.")
    finally:
        session.close()

async def check_budget_progress(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Überprüft den Fortschritt der Budgets und sendet Benachrichtigungen."""
    session = SessionLocal()
    users = session.query(User).all()

    for user in users:
        budgets = session.query(Budget).filter(Budget.user_id == user.id).all()
        for budget in budgets:
            total = session.query(func.sum(Transaction.amount)).filter(
                Transaction.user_id == user.id,
                Transaction.category == budget.name,
                Transaction.type == 'expense',
                Transaction.date >= datetime.now().replace(day=1)
            ).scalar() or 0.0

            percentage = (total / budget.limit) * 100 if budget.limit > 0 else 0
            if percentage >= 80:
                await context.bot.send_message(
                    chat_id=user.telegram_id,
                    text=f"Achtung: Du hast bereits {percentage:.1f}% deines Budgets für {budget.name} ausgegeben."
                )

    session.close()

async def check_goal_progress(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Überprüft den Fortschritt der Ziele und sendet Benachrichtigungen."""
    session = SessionLocal()
    users = session.query(User).all()

    for user in users:
        goals = session.query(Goal).filter(Goal.user_id == user.id).all()
        for goal in goals:
            progress = (goal.current_amount / goal.target_amount) * 100 if goal.target_amount > 0 else 0
            await context.bot.send_message(
                chat_id=user.telegram_id,
                text=f"Ziel-Update: {goal.name} - Fortschritt: {progress:.1f}%"
            )

    session.close()

async def get_advice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generates and sends personalized financial advice."""
    user = update.effective_user
    session = SessionLocal()
    try:
        db_user = session.query(User).filter(User.telegram_id == user.id).first()
        if not db_user:
            await update.message.reply_text("Please start the bot with /start first.")
            return

        transactions = session.query(Transaction).filter(Transaction.user_id == db_user.id).all()
        budgets = session.query(Budget).filter(Budget.user_id == db_user.id).all()
        goals = session.query(Goal).filter(Goal.user_id == db_user.id).all()

        if not transactions:
            await update.message.reply_text("You don't have any transactions yet. Add some transactions to get personalized advice.")
            return

        # Convert SQLAlchemy objects to dictionaries
        transactions_dict = [
            {
                'amount': t.amount,
                'category': t.category,
                'type': t.type,
                'date': t.date.isoformat()
            } for t in transactions
        ]
        budgets_dict = [
            {
                'name': b.name,
                'limit': b.limit
            } for b in budgets
        ]
        goals_dict = [
            {
                'name': g.name,
                'target_amount': g.target_amount,
                'current_amount': g.current_amount
            } for g in goals
        ]

        advice = get_financial_recommendations(db_user.id, transactions_dict, budgets_dict, goals_dict)
        
        # Split the advice into chunks if it's too long
        max_message_length = 4096  # Telegram's max message length
        if len(advice) <= max_message_length:
            await update.message.reply_text(f"Here are some financial recommendations for you:\n\n{advice}")
        else:
            chunks = [advice[i:i+max_message_length] for i in range(0, len(advice), max_message_length)]
            for i, chunk in enumerate(chunks):
                await update.message.reply_text(f"Financial advice (part {i+1}/{len(chunks)}):\n\n{chunk}")

    except APIError as e:
        await update.message.reply_text(f"Sorry, I couldn't generate advice at the moment: {str(e)}")
    except Exception as e:
        logger.error(f"Error in get_advice: {e}")
        await update.message.reply_text("An error occurred while generating advice. Please try again later.")
    finally:
        session.close()

async def weekly_summary(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sendet eine wöchentliche Zusammenfassung an alle Benutzer."""
    session = SessionLocal()
    users = session.query(User).all()

    for user in users:
        transactions = session.query(Transaction).filter(
            Transaction.user_id == user.id,
            Transaction.date >= datetime.now() - timedelta(days=7)
        ).all()

        total_expenses = sum(t.amount for t in transactions if t.type == 'expense')
        total_income = sum(t.amount for t in transactions if t.type == 'income')

        summary = f"Wöchentliche Zusammenfassung:\n\n"
        summary += f"Gesamtausgaben: {total_expenses}€\n"
        summary += f"Gesamteinnahmen: {total_income}€\n"
        summary += f"Bilanz: {total_income - total_expenses}€\n\n"

        top_categories = session.query(
            Transaction.category, 
            func.sum(Transaction.amount).label('total')
        ).filter(
            Transaction.user_id == user.id,
            Transaction.type == 'expense',
            Transaction.date >= datetime.now() - timedelta(days=7)
        ).group_by(Transaction.category).order_by(func.sum(Transaction.amount).desc()).limit(3).all()

        summary += "Top 3 Ausgabenkategorien:\n"
        for category, total in top_categories:
            summary += f"- {category}: {total}€\n"

        await context.bot.send_message(chat_id=user.telegram_id, text=summary)

    session.close()

async def create_monthly_budgets(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Erstellt neue Budgets für den aktuellen Monat basierend auf den Budgets des Vormonats."""
    session = SessionLocal()
    users = session.query(User).all()

    current_date = datetime.now()
    current_month = current_date.month
    current_year = current_date.year

    for user in users:
        # Hole die Budgets des Vormonats
        last_month = current_month - 1 if current_month > 1 else 12
        last_year = current_year if current_month > 1 else current_year - 1
        
        last_month_budgets = session.query(Budget).filter(
            Budget.user_id == user.id,
            Budget.year == last_year,
            Budget.month == last_month
        ).all()

        # Erstelle neue Budgets für den aktuellen Monat
        for budget in last_month_budgets:
            new_budget = Budget(
                user_id=user.id,
                name=budget.name,
                limit=budget.limit,
                year=current_year,
                month=current_month
            )
            session.add(new_budget)

        try:
            session.commit()
            await context.bot.send_message(
                chat_id=user.telegram_id,
                text=f"Neue Budgets für {calendar.month_name[current_month]} {current_year} wurden erstellt."
            )
        except Exception as e:
            logger.error(f"Fehler beim Erstellen der monatlichen Budgets für Benutzer {user.id}: {e}")
            session.rollback()

    session.close()

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles errors and logs them."""
    logger.error(f"Exception while handling an update: {context.error}")
    if isinstance(context.error, APIError):
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=str(context.error)
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="An error occurred. Please try again later."
        )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels and ends the conversation."""
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("Operation cancelled.")
    return ConversationHandler.END

# ----- Main-Funktion -----

def main() -> None:
    """Starts the Telegram bot."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("No TELEGRAM_BOT_TOKEN found in environment variables.")
        return

    application = Application.builder().token(token).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("viewbudget", view_budget))
    application.add_handler(CommandHandler("viewgoals", view_goals))
    application.add_handler(CommandHandler("report", generate_report))
    application.add_handler(CommandHandler("advice", get_advice))
    application.add_handler(CommandHandler("list", list_transactions))
    application.add_handler(CommandHandler("delete", delete_transaction))
    application.add_handler(CommandHandler("mergecategories", merge_categories))
    application.add_handler(CommandHandler("debug_api", debug_api_response))

    # Conversation handlers
    application.add_handler(ConversationHandler(
        entry_points=[CommandHandler('addexpense', add_transaction_start), CommandHandler('addincome', add_transaction_start)],
        states={
            ADD_TRANSACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_transaction_end)]
        },
        fallbacks=[CallbackQueryHandler(cancel, pattern='^cancel$')]
    ))

    application.add_handler(ConversationHandler(
        entry_points=[CommandHandler('setbudget', set_budget_start)],
        states={
            SET_BUDGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_budget_end)]
        },
        fallbacks=[CallbackQueryHandler(cancel, pattern='^cancel$')]
    ))

    application.add_handler(ConversationHandler(
        entry_points=[CommandHandler('setgoal', set_goal_start)],
        states={
            SET_GOAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_goal_end)]
        },
        fallbacks=[CallbackQueryHandler(cancel, pattern='^cancel$')]
    ))

    # Error handler
    application.add_error_handler(error_handler)

    # Scheduled jobs
    schedule_budget_check_job(application)
    application.job_queue.run_daily(check_budget_progress, time=time(hour=20, minute=0))
    application.job_queue.run_repeating(check_goal_progress, interval=timedelta(weeks=1), first=time(hour=10, minute=0, tzinfo=pytz.timezone('Europe/Berlin')))
    application.job_queue.run_repeating(weekly_summary, interval=timedelta(weeks=1), first=time(hour=9, minute=0, tzinfo=pytz.timezone('Europe/Berlin')))
    application.job_queue.run_monthly(create_monthly_budgets, when=time(hour=0, minute=1), day=1)

    # Start the Bot
    application.run_polling()

if __name__ == '__main__':
    main()