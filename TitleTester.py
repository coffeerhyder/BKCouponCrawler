from UtilsCoupons2 import coupon2FixProductTitle

""" Class to test product title replacements for type "coupons2". """

oldProductTitles = [
    "2 X-Tra Long Chili Cheese + King Fries Medium + Coca-Cola® medium",
    "King Shake Espresso medium",
    "2 MITTLERE KING POMMES ZUM PREIS VON EINER",
    "2X 6 KING NUGGETS ZUM PREIS VON EINER 6ER PORTION",
    "2 Crispy Chicken - Buy 1 get 1 free",
    "Big King",
    "Fish King",
    "KING FRIES Medium +1 DIP",
    "KING NUGGETS 6 STK. + 1 DIP"
]

for oldTitle in oldProductTitles:
    newTitle = coupon2FixProductTitle(oldTitle)
    if newTitle == oldTitle:
        print("Unchanged: " + oldTitle)
    else:
        print("Old: " + oldTitle)
        print("New: " + newTitle)
    print("---")

