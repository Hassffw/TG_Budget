from telegram.ext import Application
from telegram import Update
from telegram.ext import ContextTypes
from database import SessionLocal
from database.models import Budget, Transaction, User
from sqlalchemy import func
import logging

logger = logging.getLogger(__name__)

async def budget_check(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Überprüft die Budgets der Benutzer und sendet Warnungen bei Überschreitungen."""
    session = SessionLocal()
    budgets = session.query(Budget).all()
    for budget in budgets:
        user = session.query(User).filter(User.id == budget.user_id).first()
        if not user:
            logger.error(f"Benutzer mit ID {budget.user_id} nicht gefunden.")
            continue

        total = session.query(func.sum(Transaction.amount)).filter(
            Transaction.user_id == budget.user_id,
            Transaction.category == budget.name,  # Sicherstellen, dass `Budget.name` mit `Transaction.category` übereinstimmt
            Transaction.type == 'expense'
        ).scalar() or 0.0

        if total > budget.limit:
            try:
                await context.bot.send_message(
                    chat_id=user.telegram_id,
                    text=f"Warnung: Du hast dein Budget für {budget.name} überschritten! Limit: {budget.limit}€, Ausgaben: {total}€."
                )
            except Exception as e:
                logger.error(f"Fehler beim Senden der Warnung: {e}")
    session.close()

def schedule_budget_check_job(application: Application):
    """Plant tägliche Budgetüberprüfungen ein."""
    # Stellen Sie sicher, dass die JobQueue korrekt eingerichtet ist
    if application.job_queue is not None:
        application.job_queue.run_repeating(budget_check, interval=86400, first=0)  # Alle 24 Stunden
    else:
        logger.error("JobQueue ist nicht verfügbar. Budget-Überprüfungen können nicht geplant werden.")

def send_reminder(user_id, message):
    # Implement reminder sending logic here
    pass