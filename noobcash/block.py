
import base64
from datetime import datetime
from uuid import uuid4

from Crypto.Hash import SHA256

import noobcash
from noobcash.transaction import Transaction


class Block:
    def __init__(self, previous_hash, timestamp = None, my_hash = None, nonce = None, list_of_transactions = None):
        self.previous_hash = previous_hash
        self.timestamp = str(datetime.now()) if timestamp is None else timestamp
        self.uuid = uuid4()
        self.hash = my_hash
        self.nonce = 0 if nonce is None else nonce
        self.failed = False
        self.list_of_transactions: list[Transaction] = [] if list_of_transactions is None else list_of_transactions
        self.capacity = noobcash.CAPACITY
        self.difficulty = noobcash.DIFFICULTY
        
    def __eq__(self, other):
        if isinstance(other, Block):
            return self.hash == other.hash
        return False
        
    def to_dict(self):
        return {
            'previous_hash': self.previous_hash,
            'timestamp': self.timestamp,
            'hash': self.hash,
            'nonce': self.nonce,
            'failed': self.failed,
            'list_of_transactions': [transaction.to_dict() for transaction in self.list_of_transactions],
        }
        
    @classmethod
    def from_dictionary(cls, dictionary):
        previous_hash = dictionary['previous_hash']
        timestamp = dictionary['timestamp']
        my_hash = dictionary['hash']
        nonce = dictionary['nonce']
        list_of_transactions = [Transaction.from_dictionary(transaction_dict) for transaction_dict in dictionary['list_of_transactions']]
        
        return cls(previous_hash, timestamp, my_hash, nonce, list_of_transactions)
    
    def compute_hash(self):
        my_hash = SHA256.new()
        my_hash.update(base64.b64decode(self.previous_hash))
        my_hash.update(self.timestamp.encode('utf-8'))
        
        # Guarantees that if hash is equal then the blocks where created with the exact same constructor call
        my_hash.update(str(id(self)).encode('utf-8'))
        
        for transaction in self.list_of_transactions:
            my_hash.update(base64.b64decode(transaction.transaction_id))
            
        my_hash.update(bytes(self.nonce))
        
        return my_hash.digest()
    
    def get_transaction(self, transaction_id):
        for transaction in self.list_of_transactions:
            if transaction.transaction_id == transaction_id:
                return transaction
            
        return None
    
    def has_transaction(self, transaction_id):
        for transaction in self.list_of_transactions:
            if transaction.transaction_id == transaction_id:
                return True
            
        return False
    
    def mine(self): 
        while not self.failed:
            self.hash = self.compute_hash()
            is_hash_valid = self.validate_hash(self.hash)
            if is_hash_valid is True:
                break
            self.nonce += 1
            
        self.hash = base64.b64encode(self.hash).decode('utf-8')
        
        return self

    def validate_hash(self, tmp_hash=None):
        hash_bytearr = tmp_hash if tmp_hash is not None else base64.b64decode(self.hash)
        
        # * Start from third place to skip 0b1 which is the pattern with which all python binaries print
        hash_bin_repr = ''.join([str(bin(b))[3:] for b in hash_bytearr])
        
        # print(f"{noobcash.current_node.id}: {hash_bin_repr[:self.difficulty]} (want {'0' * self.difficulty==hash_bin_repr[:self.difficulty]})")
        
        return '0' * self.difficulty == hash_bin_repr[:self.difficulty]

    def add_transaction(self, transaction: Transaction):
        # add a transaction to the block            
        self.list_of_transactions.append(transaction)
        
    def get_length(self):
        return len(self.list_of_transactions)
