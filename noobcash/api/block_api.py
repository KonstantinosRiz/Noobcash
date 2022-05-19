from threading import Thread
from flask import Blueprint, request
import noobcash
import requests

from noobcash.block import Block

bp = Blueprint('block', __name__, url_prefix='/block')

@bp.route('/receive', methods=['POST'])
def receive():
    received_block = Block.from_dictionary(dict(request.get_json()))    
    
    handling_thread = Thread(target=noobcash.current_node.add_block_to_blockchain, args=[received_block])
    handling_thread.start()
        
    return '', 200

def broadcast_block(block: Block, ring):
    block = block.to_dict()
    
    for key, node_info in ring.items():
        if key != noobcash.current_node.id:
            r = requests.post(f"http://{node_info['ip']}:{node_info['port']}/block/receive", json=block)
            
    # print(f'{noobcash.current_node.id}: finished broadcasting')
