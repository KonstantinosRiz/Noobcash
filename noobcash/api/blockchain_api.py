import functools
import requests
import os
from noobcash import blockchain
import noobcash
from noobcash.blockchain import Blockchain
from noobcash.transaction import Transaction

from flask import Blueprint, request

bp = Blueprint('blockchain', __name__, url_prefix='/blockchain')

@bp.route('/get', methods=['POST'])
def send_blockchain():    
    hash_list = dict(request.get_json())['hash_list']
    
    partial_chain, last_consensual_hash = noobcash.current_node.get_partial_chain(hash_list)
            
    return {'partial_chain': partial_chain.to_dict(), 'last_consensual_hash': last_consensual_hash}, 200

def get_blockchain_from_node(node_ip, node_port):
    # * Send my hashes in order x2 that the other node knows to send me only the blocks after our first disagreement
    
    hash_list = [block.hash for block in noobcash.current_node.blockchain.chain]
    
    r = requests.post(f"http://{node_ip}:{node_port}/blockchain/get", json={'hash_list': hash_list})
    
    response = r.json()
    partial_chain = Blockchain.from_dictionary(response['partial_chain'])
    last_consensual_hash = response['last_consensual_hash']
    return partial_chain, last_consensual_hash