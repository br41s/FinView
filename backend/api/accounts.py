"""API endpoints for broker account management."""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from backend.api.auth import CurrentUser
from backend.database import DbSession
from backend.models import Account, Broker
from backend.services.billing_service import check_account_limit
from backend.services.import_service import delete_account_cascade

router = APIRouter(prefix="/accounts", tags=["accounts"])


# --------------- schemas ---------------


class AccountCreate(BaseModel):
    broker: str
    account_id: str
    name: str = ""
    currency: str = "EUR"


class AccountUpdate(BaseModel):
    name: str | None = None
    currency: str | None = None


class AccountOut(BaseModel):
    id: int
    broker: str
    account_id: str
    name: str
    currency: str
    transaction_count: int = 0
    import_count: int = 0

    model_config = {"from_attributes": True}


# --------------- routes ---------------


@router.get("", response_model=list[AccountOut], include_in_schema=False)
@router.get("/", response_model=list[AccountOut])
def list_accounts(db: DbSession, user: CurrentUser):
    """List all broker accounts for the current user."""
    accounts = db.query(Account).filter(Account.user_id == user.id).all()
    result = []
    for acct in accounts:
        out = AccountOut(
            id=acct.id,
            broker=acct.broker,
            account_id=acct.account_id,
            name=acct.name,
            currency=acct.currency,
            transaction_count=len(acct.transactions),
            import_count=len(acct.imports),
        )
        result.append(out)
    return result


@router.post("/", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
def create_account(data: AccountCreate, db: DbSession, user: CurrentUser):
    """Create a new broker account."""
    # Validate broker
    valid_brokers = [b.value for b in Broker]
    if data.broker not in valid_brokers:
        raise HTTPException(400, f"Invalid broker. Must be one of: {valid_brokers}")

    # Check subscription limits
    allowed = check_account_limit(db, user)
    if not allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account limit reached for your plan")

    # Check duplicate
    existing = (
        db.query(Account)
        .filter(
            Account.user_id == user.id,
            Account.broker == data.broker,
            Account.account_id == data.account_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(409, "Account already exists for this broker + account ID")

    account = Account(
        user_id=user.id,
        broker=data.broker,
        account_id=data.account_id,
        name=data.name,
        currency=data.currency,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return AccountOut(
        id=account.id,
        broker=account.broker,
        account_id=account.account_id,
        name=account.name,
        currency=account.currency,
    )


@router.patch("/{account_id}", response_model=AccountOut)
def update_account(account_id: int, data: AccountUpdate, db: DbSession, user: CurrentUser):
    """Update account name or currency."""
    account = (
        db.query(Account)
        .filter(Account.id == account_id, Account.user_id == user.id)
        .first()
    )
    if not account:
        raise HTTPException(404, "Account not found")

    if data.name is not None:
        account.name = data.name
    if data.currency is not None:
        account.currency = data.currency

    db.commit()
    db.refresh(account)
    return AccountOut(
        id=account.id,
        broker=account.broker,
        account_id=account.account_id,
        name=account.name,
        currency=account.currency,
        transaction_count=len(account.transactions),
        import_count=len(account.imports),
    )


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(account_id: int, db: DbSession, user: CurrentUser):
    """Delete an account and all its associated data."""
    account = (
        db.query(Account)
        .filter(Account.id == account_id, Account.user_id == user.id)
        .first()
    )
    if not account:
        raise HTTPException(404, "Account not found")

    delete_account_cascade(db, account_id, user.id)
    db.commit()
