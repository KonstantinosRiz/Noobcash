import functools
import requests
import os
import threading
from noobcash.exceptions import InsufficientFundsException, NegativeAmountException
from noobcash.transaction import Transaction

from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for
)

import noobcash
import noobcash.transaction
from noobcash.transaction_output import TransactionOutput

bp = Blueprint('transaction', __name__, url_prefix='/transaction')

@bp.route('/receive', methods=['POST'])
def receive():
    received_transaction = Transaction.from_dictionary(dict(request.get_json()))
    
    # print(f'Received transaction {received_transaction.transaction_id} from {noobcash.current_node.get_node_id_from_address(received_transaction.sender_address)}')
    
    handling_thread = threading.Thread(target=noobcash.current_node.validate_and_add_transaction_to_block, args=[received_transaction])
    handling_thread.start()
    
    return '', 200

@bp.route('/create', methods=['POST'])
def create():
    recipient_node_id = request.form['recipient_id']
    amount = float(request.form['amount'])
        
    try:
        transaction = noobcash.current_node.create_transaction_and_add_to_block(recipient_node_id, amount)
    except InsufficientFundsException as e:
        return str(e), 400
    except NegativeAmountException as e:
        return str(e), 401 

    broadcast_transaction(transaction)
    
    return 'Done!', 200

# @bp.route('/yeet', methods=['GET'])
# def yeet():
#     noobcash.current_node.failures_must_be_yeeted()
    
#     return '', 200

@bp.route('/get_initial_utxo', methods=['POST'])
def get_initial_utxo():
    initial_utxo = TransactionOutput.from_dictionary(dict(request.get_json()))
    noobcash.current_node.wallet.add_transaction_output(initial_utxo)
    
    return '', 200
    
def broadcast_transaction(transaction: Transaction):
    for key, node_info in noobcash.current_node.ring.items():
        if key != noobcash.current_node.id:
            # print(f"Sending transaction {transaction.transaction_id} to {node_info['ip']}:{node_info['port']}")
            r = requests.post(f"http://{node_info['ip']}:{node_info['port']}/transaction/receive", json=transaction.to_dict())
            # print(f'Transaction {transaction.transaction_id} successfully sent')
            
    # print(f'All nodes have received transaction {transaction.transaction_id}')