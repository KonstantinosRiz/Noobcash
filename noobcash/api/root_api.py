import base64
from ensurepip import bootstrap
import logging
import os
import threading
from email.errors import NoBoundaryInMultipartDefect
from time import sleep

import Crypto
import noobcash
import requests
from Crypto.Hash import SHA256
from flask import Blueprint, request
from noobcash.block import Block
from noobcash.node import Node
from noobcash.state import State
from noobcash.transaction import Transaction
from noobcash.transaction_input import TransactionInput
from noobcash.transaction_output import TransactionOutput
from noobcash.mempool import broadcast_mempool

bp = Blueprint('root', __name__, url_prefix='/')
    
@bp.route('/create_node', methods=["POST"])
def create_node():
    # Learn my port number and the number of maximum nodes
    data = request.get_json()
    ip_address = str(data['ip'])
    port_number = str(data['port'])
    bootstrap_port = str(data['bootstrap_port'])
    bootstrap_ip = str(data['bootstrap_ip'])
    
    noobcash.current_node = Node()

    noobcash.current_node.ring['0']['ip'] = bootstrap_ip
    noobcash.current_node.ring['0']['port'] = bootstrap_port
    
    # At the beginning only ring element contains the info of the bootstrap node
    # so we check if we are the bootstrap
    am_bootstrap = bootstrap_port == port_number and ip_address == bootstrap_ip

    if am_bootstrap is True:
        # Boostrap node duties:
        noobcash.current_node.create_initial_blockchain()
    else:
        while True:
            try:
                r = requests.post(f"http://{bootstrap_ip}:{bootstrap_port}/bootstrap/register",
                                data={'node_public_key': noobcash.current_node.wallet.public_key.decode("utf-8"), 'node_ip_address': ip_address, 'node_port': port_number})
                
                # print(f"http://{bootstrap_ip}:{bootstrap_port}/bootstrap/register")
                if r.status_code != 200:
                    raise RuntimeError
                
                break
            except Exception:
                pass
            
            sleep(2)
    
    Log_Format = "%(levelname)s %(asctime)s - %(message)s"
    logging.basicConfig(filename = f"metrics_{noobcash.current_node.id}.log",
                    filemode = "w",
                    format = Log_Format, 
                    level = logging.INFO)
    
    return '', 200

@bp.route('/info', methods=['GET'])
def info():
    noobcash.current_node.master_state_lock.acquire()
    active_state = noobcash.current_node.active_blocks_log[noobcash.current_node.active_block.uuid] if noobcash.current_node.active_block is not None\
                else noobcash.current_node.current_state
    
    info = {
        'id': noobcash.current_node.id,
        'balance': noobcash.current_node.wallet.balance(),
        'wallet_utxos': [utxo.to_dict() for utxo in noobcash.current_node.wallet.UTXOs],
        'wallet_stxos': list(noobcash.current_node.wallet.STXOs),
        'active_balance': sum([utxo for _, utxo in active_state.utxos[noobcash.current_node.id].items()]),
        'active_utxos': [utxo.to_dict() for _, utxo in active_state.utxos[noobcash.current_node.id].items()],
        'active_block': noobcash.current_node.active_block.to_dict() if noobcash.current_node.active_block is not None else {},
        'mining_block': noobcash.current_node.mining_block.to_dict() if noobcash.current_node.mining_block is not None else {},
        'ring': noobcash.current_node.ring,
        'blockchain': noobcash.current_node.blockchain.to_dict(),
        'current_state': noobcash.current_node.current_state.to_dict(),
        'active_state': active_state.to_dict(),
        'mempool': [transaction.to_dict() for _, transaction in noobcash.current_node.mempool.items()],
    }
    noobcash.current_node.master_state_lock.release()
    
    return info, 200

@bp.route('/balance', methods=['GET'])
def balance():
    noobcash.current_node.master_state_lock.acquire()
    current_balance = sum([utxo for _, utxo in noobcash.current_node.current_state.utxos[noobcash.current_node.id].items()])
    remaining_funds = noobcash.current_node.wallet.balance()
    noobcash.current_node.master_state_lock.release()
        
    pending = current_balance - remaining_funds
    
    if pending < 0:
        pending = 100 - remaining_funds
    
    return {'balance': remaining_funds, 'unconfirmed_spending': pending}, 200

@bp.route('/view', methods=['GET'])
def view():
    noobcash.current_node.master_state_lock.acquire()
    last_block = noobcash.current_node.blockchain.chain[-1]
    
    data = [transaction.to_dict() for transaction in last_block.list_of_transactions]
    noobcash.current_node.master_state_lock.release()
    
    return {'data': data}, 200


@bp.route('/initial_data', methods=['POST'])
def initial_data():
    data = request.get_json()
    
    ring = data['ring']
    genesis_block = Block.from_dictionary(data['genesis_block'])
    shadow_log = {key: State.from_dictionary(state) for key, state in data['shadow_log'].items()}

    noobcash.current_node.ring = ring
    noobcash.current_node.blockchain.add_block(genesis_block)
    noobcash.current_node.shadow_log = shadow_log
    noobcash.current_node.current_state = shadow_log[noobcash.current_node.blockchain.last_hash]
    for _, utxo in noobcash.current_node.current_state.utxos[noobcash.current_node.id].items():
        noobcash.current_node.wallet.add_transaction_output(utxo)
        
    mempool_thread = threading.Thread(target=broadcast_mempool)
    mempool_thread.start()
    
    return '', 200
