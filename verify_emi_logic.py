def calculate_dynamic_emi(loan_amount, total_months, interest_rate_percent, month_no):
    """
    Calculates EMI for a specific month based on Reducing Balance Method.
    
    Formula:
    Principal Constant = Loan Amount / Total Months
    Remaining Principal (at start of month) = Loan Amount - (Principal Constant * (Month No - 1))
    Interest for Month = (Remaining Principal * Interest Rate) / 100
    Total EMI = Principal Constant + Interest for Month
    """
    principal_constant = loan_amount / total_months
    
    # Calculate Remaining Principal at the START of the month
    # e.g., Month 1: 10000 - (2000 * 0) = 10000
    # e.g., Month 2: 10000 - (2000 * 1) = 8000
    remaining_principal = loan_amount - (principal_constant * (month_no - 1))
    
    interest_amount = (remaining_principal * interest_rate_percent) / 100
    
    total_emi = principal_constant + interest_amount
    
    return {
        "month": month_no,
        "principal_repayment": principal_constant,
        "remaining_principal_start": remaining_principal,
        "interest_payment": interest_amount,
        "total_emi": total_emi
    }

print("Testing User Example: 10000, 5 Months, 1% Rate")
loan = 10000
months = 5
rate = 1

for m in range(1, months + 1):
    result = calculate_dynamic_emi(loan, months, rate, m)
    print(f"Month {result['month']}: Principal={result['remaining_principal_start']}, Interest={result['interest_payment']}, EMI={result['total_emi']}")
