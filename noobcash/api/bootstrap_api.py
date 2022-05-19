from copy import deepcopy
import json
import threading
import requests
import os

from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for
)

from Crypto.Hash import SHA256
import noobcash
from noobcash.block import Block
from noobcash.mempool import broadcast_mempool
from noobcash.node import Node
from noobcash.transaction import Transaction
from noobcash.api.transaction_api import broadcast_transaction
from noobcash.transaction_input import TransactionInput
from noobcash.transaction_output import TransactionOutput

bp = Blueprint('bootstrap', __name__, url_prefix='/bootstrap')

# TODO: Make this work even when bootstrap has not yet been created
@bp.route('/register', methods=['POST'])
def register():
    
    noobcash.master_lock.acquire()
    
    if noobcash.current_node is None:
        noobcash.master_lock.release()
        return 'Bootstrap has not been initialized yet', 401
    
    
    public_key = request.form['node_public_key']
    ip_address = request.form['node_ip_address']
    port = request.form['node_port']
    
    node_id = str(len(noobcash.current_node.ring))

    noobcash.current_node.ring[node_id] = { 'ip': ip_address, 'port': port, 'public_key': public_key }
            
    send_id_to_node(ip_address, port, node_id)
    # print('node')
    if len(noobcash.current_node.ring) == int(os.getenv('NODE_NUM')):
        # print('last node')
        broadcast_initial_info(noobcash.current_node.ring, noobcash.current_node.blockchain.chain[0], noobcash.current_node.shadow_log)
        mempool_thread = threading.Thread(target=broadcast_mempool)
        mempool_thread.start()
        
        noobcash.current_node.active_block = None
        
        for node_id in noobcash.current_node.ring.keys():
            if node_id != noobcash.current_node.id:
                new_transaction = noobcash.current_node.create_transaction_and_add_to_block(node_id, amount=100)
                broadcast_transaction(new_transaction)
                
                # * Give to node its initial UTXOs
                initial_utxo = new_transaction.get_recipient_transaction_output()
                send_initial_utxo(node_id, initial_utxo)
                
        noobcash.master_lock.release()
        return '', 200
    
    noobcash.master_lock.release()

    return '', 200

@bp.route('/reset', methods=['GET'])
def reset():        
    noobcash.current_node = Node()
    
    # Boostrap node duties:        
    noobcash.current_node.create_initial_blockchain()
    
    return '', 200

def send_initial_utxo(node_id, initial_utxo: TransactionOutput):
    node_info = noobcash.current_node.ring[node_id]
    r = requests.post(f"http://{node_info['ip']}:{node_info['port']}/transaction/get_initial_utxo", json=initial_utxo.to_dict())

def send_id_to_node(node_address, node_port, node_id):
    r = requests.post(f"http://{node_address}:{node_port}/id/post", data={'node_id': node_id})

def broadcast_initial_info(ring, genesis_block, shadow_log):
    ring_dict = ring
    genesis_block_dict = genesis_block.to_dict()
    shadow_log_dict = {key: state.to_dict() for key, state in shadow_log.items()}
    
    data = {
            'ring': ring_dict,
            'genesis_block': genesis_block_dict,
            'shadow_log': shadow_log_dict 
            }
    
    for key, node_info in ring.items():
        if key != noobcash.current_node.id:
            r = requests.post(f"http://{node_info['ip']}:{node_info['port']}/initial_data", json=data)