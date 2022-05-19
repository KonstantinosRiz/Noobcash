import base64
from collections import OrderedDict

import binascii
from email.mime import base
import uuid

import Crypto
import Crypto.Random
from Crypto.Hash import SHA256
from Crypto.Cipher import AES
from Crypto.PublicKey import RSA
from Crypto.Signature import PKCS1_v1_5
from noobcash.exceptions import InsufficientFundsException, NegativeAmountException

from noobcash.transaction_input import TransactionInput
from noobcash.transaction_output import TransactionOutput

class Transaction:

    def __init__(self, sender_address, recipient_address, amount, transaction_inputs, transaction_id=None, signature=None, transaction_outputs=None):
        #self.sender_address: To public key του wallet από το οποίο προέρχονται τα χρήματα
        #self.recipient_address: To public key του wallet στο οποίο θα καταλήξουν τα χρήματα
        #self.amount: το ποσό που θα μεταφερθεί
        #self.transaction_id: το hash του transaction
        #self.transaction_inputs: λίστα από Transaction Input 
        #self.transaction_outputs: λίστα από Transaction Output 
        #selfSignature
        
        # Basic info: Who sends to whom and how much money (addresses are public keys)
        self.sender_address: str = sender_address
        self.recipient_address: str = recipient_address
        self.amount = amount
        self.transaction_inputs: list[TransactionInput] = transaction_inputs
        
        self.transaction_id: str = base64.b64encode(self.hash_function()).decode('utf-8') if transaction_id is None else transaction_id
        
        have_enough_balance = self.check_balance()
        
        if not have_enough_balance:
            raise InsufficientFundsException('Not enough balance to perform transaction')
        if self.amount < 0:
            raise NegativeAmountException('Cannot perform transaction with negative amount')
        
        self.transaction_outputs = self.compute_outputs() if transaction_outputs is None else transaction_outputs
        
        self.signature = signature

        # * Metric variable
        # self.has_been_seen = False
        
    @classmethod
    def from_dictionary(cls, dictionary):
        sender_address = dictionary['sender_address']
        recipient_address = dictionary['recipient_address']
        amount = dictionary['amount']
        transaction_id = dictionary['transaction_id']
        signature = dictionary['signature']
        # ! This only works because trans inputs and outputs are essentially identical
        transaction_inputs = [TransactionInput(TransactionOutput.from_dictionary(transaction_input_dict)) for transaction_input_dict in dictionary['transaction_inputs']]
        transaction_outputs = [TransactionOutput.from_dictionary(transaction_output_dict) for transaction_output_dict in dictionary['transaction_outputs']]
        
        return cls(sender_address, recipient_address, amount, transaction_inputs, transaction_id, signature, transaction_outputs)
        
        
    def compute_outputs(self):
        # Create the UTXOs of the transaction to be sent to the two parties
        change = sum(self.transaction_inputs) - self.amount
        change_output = TransactionOutput(self.sender_address, change, self.transaction_id)
        
        recipient_output = TransactionOutput(self.recipient_address, self.amount, self.transaction_id)
        
        return [change_output, recipient_output]
    
    def get_sender_transaction_output(self):
        return self.transaction_outputs[0]
        
    def get_recipient_transaction_output(self):
        return self.transaction_outputs[1]
        
    def check_balance(self):
        # Returns true if the sender's wallet has enough money to conduct the transaction
        total_balance = sum(self.transaction_inputs)
        
        return total_balance >= self.amount


    def hash_function(self):
        # Returns the hash-id of the transaction using sender, recipient, amount and inputs which create a unique hash
        my_hash = SHA256.new()
        my_hash.update(self.sender_address.encode('utf-8'))
        my_hash.update(self.recipient_address.encode('utf-8'))
        
        # my_hash.update(str(uuid.uuid4()).encode('utf-8'))

        for transaction_input in self.transaction_inputs:
            my_hash.update(transaction_input.recipient.encode('utf-8'))
            my_hash.update(base64.b64decode(transaction_input.parent_transaction_id))
        
        return my_hash.digest()

    def to_dict(self):
        return {
            'sender_address': self.sender_address,
            'recipient_address': self.recipient_address,
            'amount': self.amount,
            'transaction_inputs': [transaction_input.to_dict() for transaction_input in self.transaction_inputs],
            'transaction_id': self.transaction_id,
            'signature': self.signature,
            'transaction_outputs': [transaction_outputs.to_dict() for transaction_outputs in self.transaction_outputs]
        }
        

    def sign_transaction(self, private_key):
        """
        Sign transaction with private key
        """
        self.signature = base64.b64encode(PKCS1_v1_5.new(RSA.import_key(private_key)).sign(SHA256.new(base64.b64decode(self.transaction_id)))).decode('utf-8')
        
    def verify_signature(self):
        # 1) Check if data is still unchanged by re-hashing the data and comparing with the existing hash
        # 2) Check that the sender is really the one who sent me the transaction
        new_hash = base64.b64encode(self.hash_function()).decode('utf-8')
        check_1 = self.transaction_id == new_hash
        check_2 = PKCS1_v1_5.new(RSA.import_key(self.sender_address)).verify(SHA256.new(base64.b64decode(self.transaction_id)), base64.b64decode(self.signature))
        return check_1 and check_2

