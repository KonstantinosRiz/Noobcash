import noobcash
from noobcash.block import Block
from noobcash.state import State

class Blockchain:
    def __init__(self, chain=None, last_hash=None):
        self.chain: list[Block] = [] if chain is None else chain
        self.last_hash = last_hash
        
        
    def is_transaction_spent(self, transaction_id):
        has_transaction = False
        for block in self.chain:
            has_transaction = block.has_transaction(transaction_id=transaction_id)
            if has_transaction is True:
                break
            
        return has_transaction
    
    def add_block(self, block: Block):
        self.chain.append(block)
        self.last_hash = block.hash
        
        return self
    
    def get_length(self):
        return len(self.chain)
    
    def to_dict(self):
        return {
            'chain': [block.to_dict() for block in self.chain],
            'last_hash': -1 if self.last_hash is None else self.last_hash 
        }
    
    @classmethod
    def from_dictionary(cls, dictionary):
        chain = [Block.from_dictionary(block_dict) for block_dict in dictionary['chain']]
        last_hash = dictionary['last_hash']
        
        return cls(chain, last_hash)