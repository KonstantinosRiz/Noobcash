from threading import Lock
import os

import Crypto
import requests
from Crypto.Hash import SHA256
from dotenv import load_dotenv
from flask import Flask, g, request
import logging

from noobcash.node import Node
from noobcash.transaction import Transaction
from noobcash.transaction_input import TransactionInput
from noobcash.transaction_output import TransactionOutput

load_dotenv('./env/.env')

CAPACITY = int(os.getenv('CAPACITY'))
DIFFICULTY = int(os.getenv('DIFFICULTY'))
NODE_NUM = int(os.getenv('NODE_NUM'))

current_node: Node = None
master_lock: Lock = Lock()

def create_app():        
    app = Flask(__name__)

    log = logging.getLogger('werkzeug')
    log.disabled = True
    
    from noobcash.api import root_api
    app.register_blueprint(root_api.bp)
    
    from noobcash.api import bootstrap_api
    app.register_blueprint(bootstrap_api.bp)
    
    from noobcash.api import transaction_api
    app.register_blueprint(transaction_api.bp)
    
    from noobcash.api import block_api
    app.register_blueprint(block_api.bp)
    
    from noobcash.api import blockchain_api
    app.register_blueprint(blockchain_api.bp)
    
    from noobcash.api import id_api
    app.register_blueprint(id_api.bp)
    
    return app
            