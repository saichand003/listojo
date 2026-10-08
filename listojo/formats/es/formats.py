# Spanish pages price in US dollars for a US market, so numbers keep the US
# separators ($1,450 and 1.5 baths). Django's stock Spanish format would print
# "$1 450" and "1,5", which reads as a different currency to DFW renters.
# Everything else (month and day names) still comes from Django's Spanish locale.
DECIMAL_SEPARATOR = '.'
THOUSAND_SEPARATOR = ','
NUMBER_GROUPING = 3
