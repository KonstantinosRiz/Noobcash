import binascii
from typing import Set

import Crypto
import Crypto.Random
from Crypto.Hash import SHA
from Crypto.PublicKey import RSA
from Crypto.Signature import PKCS1_v1_5

import hashlib
import json
from time import time
from urllib.parse import urlparse
from uuid import uuid4

from noobcash.transaction_output import TransactionOutput

class Wallet:
    def __init__(self):
        # Generate a key pair and create an empty UTXO list (wallet hasn't participated in any transactions)
        keys = Crypto.PublicKey.RSA.generate(2048)
        
        self.public_key = keys.public_key().export_key()
        self.private_key = keys.export_key()
        self.UTXOs: list[TransactionOutput] = []
        self.STXOs: set = set()

    def balance(self):  
        # Return the balance of the wallet
        # Works because UTXOs list contains transaction outputs with __radd__ method
        return sum(self.UTXOs)

    def add_transaction_output(self, transaction_output: TransactionOutput):
        if transaction_output.id not in self.STXOs and transaction_output.id not in [utxo.id for utxo in self.UTXOs]:
            self.UTXOs.append(transaction_output)

    def get_key_pair(self):
        return (self.public_key, self.private_key)
        