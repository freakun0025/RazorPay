import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError, DataError
import os
from decimal import Decimal

from app.persistence.models.base import Base
from app.persistence.models.payment import Payment
from app.persistence.models.customer import Customer
from app.domain.recovery.states import PaymentState

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://user:password@postgres:5432/recovery_db")

@pytest.fixture(scope="module")
def engine():
    engine = create_engine(DATABASE_URL)
    Base.metadata.create_all(engine)
    yield engine

@pytest.fixture
def session(engine):
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()

def test_financial_validation_db_layer_negative_amount(session):
    # Test if DB properly rejects negative amounts using CheckConstraint
    customer = Customer(external_id="cust_fin2", email="testfin2@test.com", name="Test")
    session.add(customer)
    session.commit()

    payment = Payment(
        external_id="pay_fin_negative", customer_id=customer.id, 
        amount=Decimal("-10.00"), currency="USD", status=PaymentState.FAILED
    )
    session.add(payment)
    
    with pytest.raises(IntegrityError) as exc_info:
        session.commit()
    
    assert "chk_payment_amount_positive" in str(exc_info.value)
    session.rollback()

def test_financial_validation_db_layer_currency_length(session):
    # Test if DB rejects currency string longer than 3 characters
    customer = Customer(external_id="cust_fin3", email="testfin3@test.com", name="Test")
    session.add(customer)
    session.commit()

    payment = Payment(
        external_id="pay_fin_curr", customer_id=customer.id, 
        amount=Decimal("10.00"), currency="INVALID", status=PaymentState.FAILED
    )
    session.add(payment)
    
    with pytest.raises(DataError) as exc_info:
        session.commit()
        
    assert "value too long for type character varying(3)" in str(exc_info.value)
