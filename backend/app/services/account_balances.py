from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.repositories.transactions import (
    list_accounts_with_balance_history,
    list_balance_transactions,
)
from app.schemas import AccountMonthlyBalanceResponse

ZERO = Decimal("0.00")


def monthly_account_balances(
    db: Session,
    *,
    currency_code: str | None = None,
    account_id: int | None = None,
) -> list[AccountMonthlyBalanceResponse]:
    """Build continuous ledger-derived monthly balances for relevant accounts.

    The application has no separate opening-balance field. Consequently, the
    first recorded month begins with zero and every later carried-over value is
    exactly the preceding month's ending value. Each account owns one currency,
    so values are never combined or converted.
    """
    accounts = list_accounts_with_balance_history(
        db,
        currency_code=currency_code,
        account_id=account_id,
    )
    transactions = list_balance_transactions(db, account_ids=[account.id for account in accounts])
    if not transactions:
        return []

    first_month = _month_start(min(item.transaction_date for item in transactions))
    last_month = _month_start(max(item.transaction_date for item in transactions))
    months = list(_calendar_months(first_month, last_month))
    monthly_changes: dict[tuple[int, date], Decimal] = defaultdict(lambda: ZERO)
    for transaction in transactions:
        key = (transaction.account_id, _month_start(transaction.transaction_date))
        monthly_changes[key] += _balance_effect(
            transaction_type=transaction.transaction_type,
            amount=transaction.amount,
        )

    rows: list[AccountMonthlyBalanceResponse] = []
    running_balances = {account.id: ZERO for account in accounts}
    for month in months:
        for account in accounts:
            carried_over = running_balances[account.id]
            monthly_change = monthly_changes[(account.id, month)]
            ending_balance = carried_over + monthly_change
            rows.append(
                AccountMonthlyBalanceResponse(
                    month=month.strftime("%Y-%m"),
                    account_id=account.id,
                    account_name=account.name,
                    currency_code=account.currency_code,
                    carried_over=carried_over,
                    monthly_change=monthly_change,
                    ending_balance=ending_balance,
                )
            )
            running_balances[account.id] = ending_balance

    # Newest months are consumed first by the overview, while account names
    # remain in ascending display order inside each month.
    return sorted(
        rows,
        key=lambda row: (
            -int(row.month.replace("-", "")),
            row.account_name.casefold(),
            row.account_id,
        ),
    )


def _balance_effect(*, transaction_type: str, amount: Decimal) -> Decimal:
    """Apply the same account-balance sign rules used throughout the UI."""
    return -amount if transaction_type == "expense" else amount


def _month_start(value: date) -> date:
    return date(value.year, value.month, 1)


def _calendar_months(first: date, last: date):
    """Yield inclusive calendar month starts without timezone assumptions."""
    current = first
    while current <= last:
        yield current
        current = date(current.year + (current.month == 12), current.month % 12 + 1, 1)
