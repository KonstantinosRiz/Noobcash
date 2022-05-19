from copy import deepcopy

from noobcash.transaction_output import TransactionOutput

class State:
    def __init__(self, utxos, processed_transactions):
        self.utxos: dict[str, dict[str, TransactionOutput]] = deepcopy(utxos)
        self.processed_transactions: set[str] = deepcopy(processed_transactions)
        
    def to_dict(self):
        return {
            'utxos': State.utxos_to_dict(self.utxos),
            'processed_transactions': list(self.processed_transactions)
        }
        
    @classmethod
    def from_dictionary(cls, dictionary):
        utxos = State.utxos_from_dict(dictionary['utxos'])
        processed_transactions = set(dictionary['processed_transactions'])
        
        return cls(utxos, processed_transactions)
    
    @staticmethod
    def utxos_to_dict(utxos: dict):
        utxos_copy = deepcopy(utxos)
        
        for key, utxo_dict in utxos.items():
            utxos_copy[key] = {utxo_id: utxo.to_dict() for utxo_id, utxo in utxo_dict.items()}
            
        return utxos_copy
        
    @staticmethod
    def utxos_from_dict(utxos: dict[str, dict[str, dict]]) -> dict[str, dict[str, TransactionOutput]]:
        for key, utxo_dict in utxos.items():
            utxos[key] = {utxo_id: TransactionOutput.from_dictionary(utxo) for utxo_id, utxo in utxo_dict.items()}
            
        return utxos