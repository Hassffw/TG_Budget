import matplotlib.pyplot as plt
from sqlalchemy.orm import sessionmaker
from database import engine
from database.models import Transaction
import os

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def generate_financial_report(user_id: int) -> str:
    """
    Generiert einen Diagrammbericht der Ausgaben und Einnahmen des Benutzers und gibt den Pfad zum Bild zurück.
    """
    session = SessionLocal()
    transactions = session.query(Transaction).filter(Transaction.user_id == user_id).all()

    session.close()

    if not transactions:
        raise ValueError("Keine Transaktionen gefunden.")

    # Aggregiere die Ausgaben und Einnahmen nach Kategorie
    expense_data = {}
    income_data = {}
    for tx in transactions:
        if tx.type == 'expense':
            expense_data[tx.category] = expense_data.get(tx.category, 0) + tx.amount
        else:
            income_data[tx.category] = income_data.get(tx.category, 0) + tx.amount

    # Erstelle zwei Tortendiagramme
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))

    # Ausgaben
    if expense_data:
        ax1.pie(expense_data.values(), labels=expense_data.keys(), autopct='%1.1f%%', startangle=90)
        ax1.set_title('Ausgaben nach Kategorie')
    else:
        ax1.text(0.5, 0.5, 'Keine Ausgaben', ha='center', va='center')

    # Einnahmen
    if income_data:
        ax2.pie(income_data.values(), labels=income_data.keys(), autopct='%1.1f%%', startangle=90)
        ax2.set_title('Einnahmen nach Kategorie')
    else:
        ax2.text(0.5, 0.5, 'Keine Einnahmen', ha='center', va='center')

    plt.tight_layout()

    # Speichere das Diagramm als Bild
    report_path = f"financial_report_{user_id}.png"
    plt.savefig(report_path)
    plt.close()

    return report_path

# Die alte generate_expense_report Funktion kann entfernt oder umbenannt werden