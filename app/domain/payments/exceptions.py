class ImmutableAttributeError(Exception):
    pass

class InvalidFinancialPayload(Exception):
    pass

def validate_financials(amount, currency):
    if amount < 0:
        raise InvalidFinancialPayload("Amount cannot be negative")
    if currency.upper() not in ("USD", "EUR", "GBP", "INR"):
        raise InvalidFinancialPayload("Unsupported currency")
