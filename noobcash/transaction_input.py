import base64
from noobcash.transaction_output import TransactionOutput

class TransactionInput(TransactionOutput):
    def __init__(self, transaction_output: TransactionOutput) -> None:
        # public key of recipient
        self.recipient = transaction_output.recipient
        
        # coupon amount
        self.value = transaction_output.value
        
        # parent id
        self.parent_transaction_id = transaction_output.parent_transaction_id
        
        self.id = transaction_output.id
