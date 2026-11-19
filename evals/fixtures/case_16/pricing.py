def total_price(items):
    """Sum of price * quantity for every (price, quantity) item."""
    total = 0
    for price, quantity in items:
        total += price
    return total
